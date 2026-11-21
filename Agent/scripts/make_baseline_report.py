"""results.json에서 Markdown 리포트를 만든다.

  python -m scripts.make_baseline_report                 # 가장 최근 runs/eval_*/results.json
  python -m scripts.make_baseline_report runs\\eval_x\\results.json
"""

import argparse
import json
from pathlib import Path

from core.eval_report import render_baseline_markdown

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="?", help="results.json 경로 (생략하면 가장 최근 평가)")
    ap.add_argument("--out", default=str(ROOT / "reports" / "baseline_sync_fifo.md"))
    args = ap.parse_args()

    if args.results:
        src = Path(args.results)
    else:
        found = sorted((ROOT / "runs").glob("eval_*/results.json"))
        if not found:
            print("runs/eval_*/results.json이 없습니다. 먼저 python -m scripts.run_eval을 실행하세요.")
            return 1
        src = found[-1]
    report = json.loads(src.read_text(encoding="utf-8"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_baseline_markdown(report), encoding="utf-8")
    print(f"입력: {src}\n출력: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())