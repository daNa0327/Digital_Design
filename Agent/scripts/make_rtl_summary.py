"""RTL Analyzer 5-4 요약(JSON)을 만든다. TB Generator(LLM)에 넘길 입력과 같은 형식이다.

사용:
    python -m scripts.make_rtl_summary dut/sync_fifo/rtl
    python -m scripts.make_rtl_summary Manual_test/dut --out reports/rtl_summary_async_fifo.json
    python -m scripts.make_rtl_summary some_dir --top my_top
"""

import argparse
import json
import sys
from pathlib import Path

from core.rtl_summary import summarize_rtl, validate_summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="파일 또는 폴더")
    ap.add_argument("--top", help="top 모듈 이름 (생략하면 자동 추정)")
    ap.add_argument("--out", help="JSON을 저장할 경로 (생략하면 화면에 출력)")
    a = ap.parse_args(argv)

    files: list[Path] = []
    for p in map(Path, a.paths):
        files += sorted(list(p.rglob("*.v")) + list(p.rglob("*.sv"))) if p.is_dir() else [p]
    if not files:
        print("Verilog 파일(.v/.sv)을 찾지 못했습니다.", file=sys.stderr)
        return 2

    summary = summarize_rtl(files, top=a.top)
    problems = validate_summary(summary)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if a.out:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"저장: {out}")
    else:
        print(text)

    print(f"\ntop: {summary['top']}   ready_for_tb: {summary['ready_for_tb']}", file=sys.stderr)
    for b in summary["blockers"]:
        print(f"BLOCKER: {b}", file=sys.stderr)
    for n in summary["notes"]:
        print(f"NOTE: {n}", file=sys.stderr)
    for p in problems:
        print(f"SCHEMA: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())