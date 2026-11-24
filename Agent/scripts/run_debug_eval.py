"""Debug Agent 평가 실행: 사람 TB가 실패시킨 RTL 변형에서 Agent가 원인 위치를 맞히는지 잰다.

  python -m scripts.run_debug_eval --dry-run                 # 호출하지 않고 계획과 예상 호출 수만 출력
  python -m scripts.run_debug_eval --only B07 B17            # 일부만 (처음엔 2~3개로 규약이 지켜지는지 확인)
  python -m scripts.run_debug_eval                           # 전체 (Vivado + Gemini 호출 필요)
  python -m scripts.run_debug_eval --resume                  # 한도로 멈췄다면 가장 최근 폴더에서 이어서

결과: runs/dbgeval_<label>_<시각>/results.json, cases/<id>.json, reports/debug_eval_<dut>_<label>.md
LLM 응답은 디스크 캐시에 저장되어, 같은 입력의 재실행은 호출 한도를 쓰지 않는다.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from core.bugs import load_catalog
from core.debug_eval import render_markdown, run_debug_eval
from core.evaluator import xsim_runner
from llm.base import LLMError
from llm.config import ConfigError, make_client

ROOT = Path(__file__).resolve().parents[1]
EST_CALLS_PER_BUG = 6          # 도구 4~5회 + 보고서 1회 (실측 전 가정)


def latest_out(root: Path, label: str) -> Path | None:
    found = sorted((root / "runs").glob(f"dbgeval_{label}_*"))
    return found[-1] if found else None


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=str(ROOT / "bugs" / "sync_fifo" / "bugs.json"))
    ap.add_argument("--only", nargs="*", help="id에 이 문자열이 포함된 변형만 실행")
    ap.add_argument("--label", default="human", help="결과 폴더/리포트 이름에 쓸 라벨 (기본: human)")
    ap.add_argument("--tb", help="입력 TB (기본: 사람이 쓴 dut/sync_fifo/tb/tb_sync_fifo_sc.v)")
    ap.add_argument("--tb-top", help="TB의 top 모듈 이름 (기본: 카탈로그의 top)")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--near", type=int, default=2, help="정답 줄에서 이만큼 떨어진 것까지 near로 인정")
    ap.add_argument("--out", help="결과 폴더 (기본: runs/dbgeval_<label>_<시각>)")
    ap.add_argument("--report", help="마크다운 리포트 경로 (기본: reports/debug_eval_<dut>_<label>.md)")
    ap.add_argument("--resume", action="store_true", help="--out(없으면 가장 최근 폴더)의 끝난 케이스는 건너뜀")
    ap.add_argument("--no-spec", action="store_true", help="spec.md를 Agent에게 주지 않음")
    ap.add_argument("--no-cache", action="store_true", help="LLM 디스크 캐시를 쓰지 않음 (호출 한도를 씀)")
    ap.add_argument("--dry-run", action="store_true", help="실행하지 않고 계획과 예상 호출 수만 출력")
    a = ap.parse_args(argv)

    meta = json.loads(Path(a.catalog).read_text(encoding="utf-8"))
    bugs = load_catalog(a.catalog)
    if a.only:
        bugs = [b for b in bugs if any(s in b.id for s in a.only)]
    real = [b for b in bugs if not b.equivalent]
    golden_dir = ROOT / meta["golden_rtl"]
    tb = Path(a.tb) if a.tb else golden_dir.parent / "tb" / "tb_sync_fifo_sc.v"
    tb_top = a.tb_top or meta["top"]
    spec_path = golden_dir.parent / "spec.md"
    spec = spec_path.read_text(encoding="utf-8") if (spec_path.is_file() and not a.no_spec) else None

    if a.out:
        out = Path(a.out)
    elif a.resume:
        out = latest_out(ROOT, a.label)
        if out is None:
            print(f"이어갈 폴더가 없습니다 (runs/dbgeval_{a.label}_*). --out을 지정하거나 --resume 없이 실행하세요.")
            return 2
    else:
        out = ROOT / "runs" / f"dbgeval_{a.label}_{time.strftime('%Y%m%d_%H%M%S')}"

    est = len(real) * EST_CALLS_PER_BUG
    print(f"DUT {meta['dut']}: 평가 대상 {len(real)}개 (동등 변형 {len(bugs) - len(real)}개 제외)")
    print(f"입력 TB: {tb} (top {tb_top}), spec {'사용' if spec else '미사용'}, 최대 단계 {a.max_steps}")
    print(f"예상 LLM 호출: 약 {est}회 (가정: 변형당 {EST_CALLS_PER_BUG}회, 실측 전). 무료 등급 일일 상한과 비교하세요 (python -m scripts.llm_ping).")
    print(f"결과 폴더: {out}")
    if a.dry_run:
        return 0
    if not tb.is_file():
        print(f"TB 파일이 없습니다: {tb}")
        return 2

    try:
        client = make_client(use_cache=not a.no_cache)
    except (ConfigError, LLMError) as e:
        print(f"LLM 설정 오류: {e}")
        return 2

    t0 = time.time()
    try:
        report = run_debug_eval(bugs, golden_dir, tb, tb_top, meta["dut"], xsim_runner(), client, out / "work",
                                dut=meta["dut"], spec_text=spec, max_steps=a.max_steps, near=a.near,
                                resume=a.resume, progress=lambda s: print(s, flush=True))
    except FileNotFoundError as e:
        print(f"Vivado 도구를 찾지 못했습니다 (PATH 확인): {e}")
        return 2
    report.meta["label"] = a.label
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    rp = Path(a.report) if a.report else ROOT / "reports" / f"debug_eval_{meta['dut']}_{a.label}.md"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(render_markdown(report, a.label), encoding="utf-8")

    s = report.summary
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"          # noqa: E731
    print()
    print(f"평가 {s['n_evaluated']}개: 정확한 줄 {pct(s['exact_rate'])}, ±{a.near}줄 이내 {pct(s['located_rate'])}, "
          f"파일 {pct(s['file_accuracy'])}, 보고서 {pct(s['report_rate'])}")
    print(f"LLM 호출 {s['llm_calls']}회 (캐시 {s['cached_calls']}회), 형식 오류율 {pct(s['format_error_rate'])}, "
          f"거부된 보고서 {s['rejected_reports']}개  ({time.time() - t0:.0f}초)")
    print(f"결과: {out / 'results.json'}\n리포트: {rp}")
    if report.aborted_reason:
        print(f"\n중간에 멈춤: {report.aborted_reason}\n같은 명령에 --resume을 붙여 한도가 초기화된 뒤 이어서 실행하세요.")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())