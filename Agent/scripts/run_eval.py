"""평가 하네스 실행: 골든과 버그 변형 전체를 Vivado로 돌려 results.json을 만든다.

  python -m scripts.run_eval                      # 전체 (약 3분)
  python -m scripts.run_eval --only B07 B17       # id에 포함된 문자열로 일부만
"""

import argparse
import json
import sys
import time
from pathlib import Path

from core.bugs import load_catalog
from core.evaluator import evaluate, xsim_runner

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=str(ROOT / "bugs" / "sync_fifo" / "bugs.json"))
    ap.add_argument("--only", nargs="*", help="id에 이 문자열이 포함된 변형만 실행")
    ap.add_argument("--out", help="결과 폴더 (기본: runs/eval_<시각>)")
    args = ap.parse_args(argv)

    meta = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    bugs = load_catalog(args.catalog)
    if args.only:
        bugs = [b for b in bugs if any(s in b.id for s in args.only)]
    golden_dir = ROOT / meta["golden_rtl"]
    tb = golden_dir.parent / "tb" / "tb_sync_fifo_sc.v"
    out = Path(args.out) if args.out else ROOT / "runs" / time.strftime("eval_%Y%m%d_%H%M%S")

    t0 = time.time()
    report = evaluate(bugs, golden_dir, tb, meta["top"], xsim_runner(), out / "work",
                      dut=meta["dut"], progress=lambda s: print(s, flush=True))
    d = report.to_dict()
    (out / "results.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"golden    : {d['golden']['status']} (tb_verdict={d['golden']['tb_verdict']})")
    if report.aborted:
        print("골든이 PASS가 아니라 중단했습니다. 변형은 실행하지 않았습니다.")
        return 1
    print(f"{'bug':28s} {'type':8s} {'outcome':28s} {'status':6s} first_fail")
    for r in report.results:
        ff = f"{r.first_fail_signal}@{r.first_fail_time_ps}ps" if r.first_fail_signal else "-"
        print(f"{r.bug_id:28s} {r.type:8s} {r.outcome:28s} {r.status:6s} {ff}")
    s = d["summary"]
    score = "n/a" if s["mutation_score"] is None else f"{s['mutation_score']:.1%}"
    print(f"\ndetected={s['detected']} survived={s['survived']} invalid={s['invalid']} "
          f"equivalent_ok={s['equivalent_ok']}  mutation_score={score}  ({time.time() - t0:.0f}s)")
    if s["survivors"]:
        print("survivors (TB가 못 잡음):", ", ".join(s["survivors"]))
    if s["problems"]:
        print("문제(변형 오류/동등 메타데이터 오류):", ", ".join(s["problems"]))
    print(f"결과: {out / 'results.json'}")
    return 1 if s["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())