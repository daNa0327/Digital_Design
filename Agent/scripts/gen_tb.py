"""TB Generator 6-2: RTL로 TB를 생성하고 정적 검사한다 (컴파일/시뮬레이션은 6-3 이후).

사용:
    # 프롬프트만 만들어 저장 (LLM 호출 없음, 호출량 0) - 먼저 이것으로 프롬프트를 눈으로 확인
    python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --spec dut/sync_fifo/README.md --dry-run

    # 실제 생성 (RVA_LLM_* 설정 필요, 호출 1회, 같은 입력이면 캐시)
    python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --spec dut/sync_fifo/README.md \\
        --out runs/tb/sync_fifo_llm.v

    # 이미 있는 TB 파일만 검사 (사람 TB, 또는 Gemini 앱 등에서 받아 온 코드)
    python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --check dut/sync_fifo/tb/tb_sync_fifo_sc.v
"""

import argparse
import sys
from pathlib import Path

from core.rtl_summary import summarize_rtl
from core.tb_check import check_tb, errors_of
from core.tb_generator import generate_tb, save_tb
from core.tb_prompt import TBPromptError, build_tb_prompt, load_sources
from llm.base import LLMError
from llm.config import ConfigError, load_env, make_client


def _collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        files += sorted(list(p.rglob("*.v"))) if p.is_dir() else [p]
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="DUT RTL 파일 또는 폴더 (TB는 넣지 않음)")
    ap.add_argument("--top", help="top 모듈 이름 (생략하면 자동 추정)")
    ap.add_argument("--spec", help="명세 텍스트 파일 (생략하면 RTL에서 동작을 유도하고 가정을 주석으로 남김)")
    ap.add_argument("--out", help="생성한 TB를 저장할 경로")
    ap.add_argument("--dry-run", action="store_true", help="프롬프트만 만들고 LLM은 부르지 않음")
    ap.add_argument("--check", metavar="TB_FILE", help="기존 TB 파일만 정적 검사")
    ap.add_argument("--model", help="이번 호출만 모델 지정 (기본은 RVA_LLM_MODEL)")
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
        issues = check_tb(Path(a.check).read_text(encoding="utf-8"), summary)
        for i in issues:
            print(i)
        print(f"검사 결과: error {len(errors_of(issues))}개, warning {len(issues) - len(errors_of(issues))}개")
        return 1 if errors_of(issues) else 0

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
        result = generate_tb(summary, sources, client, spec_text=spec, model=a.model)
    except (TBPromptError, ConfigError, LLMError) as e:
        print(f"실패: {type(e).__name__}: {e}", file=sys.stderr)
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
