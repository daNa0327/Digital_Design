"""평가 하네스 실행: 골든과 버그 변형 전체를 Vivado로 돌려 results.json을 만든다.

  python -m scripts.run_eval                      # 전체 (약 3분)
  python -m scripts.run_eval --only B07 B17       # id에 포함된 문자열로 일부만

  # 다른 TB(예: LLM이 만든 TB)를 같은 변형 세트로 평가: 결과는 runs/tbeval_<label>_<시각>/ 에 저장
  python -m scripts.run_eval --tb runs/tb/sync_fifo_llm_gated.v --label llm
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from core.bugs import load_catalog
from core.compile_gate import tb_top_of
from core.evaluator import evaluate, xsim_runner

ROOT = Path(__file__).resolve().parents[1]


def resolve_run(args, meta: dict, root: Path):
    """평가할 TB 경로, TB top 이름, 결과 폴더를 정한다.

    --tb가 없으면 기존 기준 TB(사람이 쓴 self-checking TB)를 쓰고 결과는 runs/eval_<시각>/ (기존과 동일).
    --tb가 있으면 TB top은 코드에서 읽고(--tb-top으로 덮어쓰기 가능), 결과는 runs/tbeval_<label>_<시각>/ 이다.
    접두를 달리하는 이유: make_baseline_report가 runs/eval_*의 최신을 기준선으로 쓰므로 섞이지 않게 하기 위함.
    """
    golden_dir = root / meta["golden_rtl"]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    if not args.tb:
        tb = golden_dir.parent / "tb" / "tb_sync_fifo_sc.v"
        top = args.tb_top or meta["top"]
        out = Path(args.out) if args.out else root / "runs" / f"eval_{stamp}"
        return golden_dir, tb, top, out
    tb = Path(args.tb)
    if not tb.is_file():
        raise SystemExit(f"TB 파일이 없습니다: {tb}")
    top = args.tb_top or tb_top_of(tb.read_text(encoding="utf-8"))
    if not top:
        raise SystemExit("TB 파일에서 module 이름을 찾지 못했습니다 (--tb-top으로 지정하세요)")
    label = args.label or tb.stem
    out = Path(args.out) if args.out else root / "runs" / f"tbeval_{label}_{stamp}"
    return golden_dir, tb, top, out


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=str(ROOT / "bugs" / "sync_fifo" / "bugs.json"))
    ap.add_argument("--only", nargs="*", help="id에 이 문자열이 포함된 변형만 실행")
    ap.add_argument("--out", help="결과 폴더 (기본: runs/eval_<시각>, --tb를 쓰면 runs/tbeval_<label>_<시각>)")
    ap.add_argument("--tb", help="평가할 TB 파일 (기본: 사람이 쓴 dut/sync_fifo/tb/tb_sync_fifo_sc.v)")
    ap.add_argument("--tb-top", help="TB의 top 모듈 이름 (--tb를 쓰면 코드에서 자동으로 읽음)")
    ap.add_argument("--label", help="결과 폴더 이름에 쓸 라벨 (기본: TB 파일 이름)")
    args = ap.parse_args(argv)

    meta = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    bugs = load_catalog(args.catalog)
    if args.only:
        bugs = [b for b in bugs if any(s in b.id for s in args.only)]
    golden_dir, tb, tb_top, out = resolve_run(args, meta, ROOT)
    print(f"TB: {tb} (top {tb_top})")

    t0 = time.time()
    report = evaluate(bugs, golden_dir, tb, tb_top, xsim_runner(), out / "work",
                      dut=meta["dut"], progress=lambda s: print(s, flush=True))
    d = report.to_dict()
    # 어떤 TB로 평가했는지 결과에 남긴다 (기존 리포트 생성기는 모르는 키를 무시함)
    d["tb"] = {"path": tb.as_posix(), "top": tb_top, "label": args.label,
               "sha256": hashlib.sha256(tb.read_bytes()).hexdigest()[:12]}
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