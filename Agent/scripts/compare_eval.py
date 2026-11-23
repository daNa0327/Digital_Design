"""두 TB의 평가 결과(results.json)를 비교해 Markdown 리포트를 만든다.

  python -m scripts.compare_eval runs\\eval_20261120_101500\\results.json runs\\tbeval_llm_20261123_160000\\results.json \\
      --label-a human --label-b llm
"""

import argparse
import json
from pathlib import Path

from core.eval_compare import compare_reports, render_comparison_markdown

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", help="기준(A) results.json, 보통 사람이 쓴 TB")
    ap.add_argument("b", help="비교(B) results.json, 보통 LLM TB")
    ap.add_argument("--label-a", default="human")
    ap.add_argument("--label-b", default="llm")
    ap.add_argument("--out", default=str(ROOT / "reports" / "compare_sync_fifo.md"))
    args = ap.parse_args(argv)

    ra = json.loads(Path(args.a).read_text(encoding="utf-8"))
    rb = json.loads(Path(args.b).read_text(encoding="utf-8"))
    cmp = compare_reports(ra, rb)
    md = render_comparison_markdown(cmp, args.label_a, args.label_b, ra.get("tb"), rb.get("tb"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    sa, sb = cmp["summary"]["a"], cmp["summary"]["b"]
    f = lambda s: "n/a" if s["mutation_score"] is None else f"{s['mutation_score']:.1%}"   # noqa: E731
    print(f"{args.label_a}: mutation_score={f(sa)}   {args.label_b}: mutation_score={f(sb)}")
    print(f"{args.label_a}만 잡음: {cmp['only_a'] or '없음'}\n{args.label_b}만 잡음: {cmp['only_b'] or '없음'}")
    print(f"출력: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())