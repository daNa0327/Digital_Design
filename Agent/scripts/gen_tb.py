"""TB Generator 6-2: RTL로 TB를 생성하고 정적 검사한다 (컴파일/시뮬레이션은 6-3 이후).

사용:
    # 프롬프트만 만들어 저장 (LLM 호출 없음, 호출량 0) - 먼저 이것으로 프롬프트를 눈으로 확인
    python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --spec dut/sync_fifo/README.md --dry-run

    # 실제 생성 (RVA_LLM_* 설정 필요, 호출 1회, 같은 입력이면 캐시)
    python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --spec dut/sync_fifo/README.md \\
        --out runs/tb/sync_fifo_llm.v

    # 생성 + 컴파일 게이트(xvlog/xelab, Vivado 필요) + 실패 시 에러를 되먹여 재생성 (호출 최대 --max-attempts회)
    python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --spec dut/sync_fifo/spec.md --gate \\
        --out runs/tb/sync_fifo_llm.v

    # 이미 있는 TB 파일만 검사 (사람 TB, 또는 Gemini 앱 등에서 받아 온 코드). --compile을 붙이면 컴파일도 확인
    python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --check runs/tb/sync_fifo_llm.v --compile
"""

import argparse
import sys
from pathlib import Path

from core.compile_gate import compile_check
from core.rtl_summary import summarize_rtl
from core.tb_check import check_tb, errors_of
from core.tb_generator import generate_tb, save_tb
from core.tb_prompt import TBPromptError, build_tb_prompt, load_sources
from core.tb_repair import generate_with_gate
from llm.base import LLMError
from llm.config import ConfigError, load_env, make_client


def _collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        files += sorted(list(p.rglob("*.v"))) if p.is_dir() else [p]
    return files


def _run_gate(a, summary, sources, spec, client, files) -> int:
    """생성 -> 정적 검사 -> 컴파일 -> (실패) 되먹임 재시도. 모든 시도의 요약과 최종 결과를 출력한다."""
    def compile_fn(code, top):
        return compile_check(files, code, top, a.work_root, sv=a.sv)

    def show(att):
        tb, cr = att.tb, att.compile
        state = "통과" if att.ok else "실패"
        comp = "건너뜀" if cr is None else ("통과" if cr.ok else f"실패({cr.stage})")
        print(f"[시도 {att.n}] {state}  정적 error {len([i for i in tb.issues if i.level == 'error'])}개 / 컴파일 {comp}"
              f"  토큰 {tb.input_tokens}/{tb.output_tokens}  캐시 {tb.cached}")
        for p in att.problems:
            print("   - " + p.replace("\n", "\n     "))

    run = generate_with_gate(summary, sources, client, compile_fn, spec_text=spec, max_attempts=a.max_attempts,
                             model=a.model, on_attempt=show)
    if run.final.code:
        out = save_tb(run.final, a.out or f"runs/tb/{run.final.tb_name}.v")
        print(f"저장: {out}")
    print(f"결과: {'게이트 통과' if run.ok else '게이트 실패'}  (시도 {len(run.attempts)}/{run.max_attempts}, "
          f"실제 LLM 호출 {run.llm_calls}회)")
    return 0 if run.ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="DUT RTL 파일 또는 폴더 (TB는 넣지 않음)")
    ap.add_argument("--top", help="top 모듈 이름 (생략하면 자동 추정)")
    ap.add_argument("--spec", help="명세 텍스트 파일 (생략하면 RTL에서 동작을 유도하고 가정을 주석으로 남김)")
    ap.add_argument("--out", help="생성한 TB를 저장할 경로")
    ap.add_argument("--dry-run", action="store_true", help="프롬프트만 만들고 LLM은 부르지 않음")
    ap.add_argument("--check", metavar="TB_FILE", help="기존 TB 파일만 정적 검사")
    ap.add_argument("--model", help="이번 호출만 모델 지정 (기본은 RVA_LLM_MODEL)")
    ap.add_argument("--gate", action="store_true", help="컴파일 게이트(xvlog/xelab)를 통과할 때까지 에러를 되먹여 재생성")
    ap.add_argument("--max-attempts", type=int, default=3, help="--gate의 최대 시도(=LLM 호출) 수, 기본 3")
    ap.add_argument("--compile", action="store_true", help="--check와 함께: 정적 검사 뒤 컴파일도 확인")
    ap.add_argument("--sv", action="store_true", help="게이트를 평가 흐름처럼 xvlog -sv로 실행 (기본은 Verilog 모드)")
    ap.add_argument("--work-root", default="runs/tb_gate", help="게이트 작업 폴더 (기본 runs/tb_gate)")
    a = ap.parse_args(argv)

    files = _collect(a.paths)
    if not files:
        print("Verilog 파일을 찾지 못했습니다.", file=sys.stderr)
        return 2
    summary = summarize_rtl(files, top=a.top)
    print(f"top: {summary['top']}   ready_for_tb: {summary['ready_for_tb']}")
    for b in summary["blockers"]:
        print(f"BLOCKER: {b}", file=sys.stderr)

    if a.check:
        code = Path(a.check).read_text(encoding="utf-8")
        issues = check_tb(code, summary)
        for i in issues:
            print(i)
        print(f"정적 검사: error {len(errors_of(issues))}개, warning {len(issues) - len(errors_of(issues))}개")
        bad = bool(errors_of(issues))
        if a.compile:
            try:
                cr = compile_check(files, code, None, a.work_root, sv=a.sv)
            except FileNotFoundError as e:
                print(f"실패: Vivado 도구를 찾지 못함 ({e}) - PATH를 확인하세요", file=sys.stderr)
                return 1
            for e in cr.primary_errors() if not cr.ok else []:
                print(f"  {e}")
            print(f"컴파일({'-sv' if a.sv else 'Verilog'}): {'통과' if cr.ok else '실패 (' + str(cr.stage) + ')'}  [{cr.duration_s:.1f}s]")
            bad = bad or not cr.ok
        return 1 if bad else 0

    try:
        sources = load_sources(summary)
        spec = Path(a.spec).read_text(encoding="utf-8") if a.spec else None
        if a.dry_run:
            system, prompt = build_tb_prompt(summary, sources, spec)
            out = Path(a.out or "runs/tb/prompt.txt")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("# SYSTEM\n" + system + "\n\n# PROMPT\n" + prompt + "\n", encoding="utf-8")
            print(f"프롬프트 저장: {out}   (약 {len((system + prompt).split())} 단어, 호출 없음)")
            return 0
        load_env()
        client = make_client()
        if a.gate:
            return _run_gate(a, summary, sources, spec, client, files)
        result = generate_tb(summary, sources, client, spec_text=spec, model=a.model)
    except (TBPromptError, ConfigError, LLMError) as e:
        print(f"실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"실패: 파일 또는 Vivado 도구를 찾지 못함 ({e})", file=sys.stderr)
        return 1

    print(f"모델: {result.model}   토큰: 입력 {result.input_tokens} / 출력 {result.output_tokens}   "
          f"캐시: {result.cached}   종료: {result.finish_reason}")
    for n in result.extract_notes:
        print(f"[추출] {n}")
    for i in result.issues:
        print(i)
    if result.code:
        out = save_tb(result, a.out or f"runs/tb/{result.tb_name}.v")
        print(f"저장: {out}")
    print("정적 검사:", "통과 (컴파일은 6-3에서 확인)" if result.ok else "실패")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())