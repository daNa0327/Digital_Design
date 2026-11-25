"""평가 결과 케이스의 Agent 수정안(diff)을 출력한다.

  python -m scripts.show_proposals --results runs/dbgeval_v0d_... B03 B13 B14 B05
"""

import argparse
import json
import sys
from pathlib import Path


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="평가 결과 폴더")
    ap.add_argument("ids", nargs="+", help="버그 ID 또는 접두사 (예: B03)")
    a = ap.parse_args(argv)
    res = Path(a.results)
    cdir = next((d for d in (res / "work" / "cases", res / "cases") if d.is_dir()), None)
    if cdir is None:
        print(f"케이스 폴더를 찾지 못했습니다: {res}")
        return 2
    for want in a.ids:
        files = sorted(cdir.glob(f"{want}*.json"))
        if not files:
            print(f"== {want}: 없음")
        for f in files:
            c = json.loads(f.read_text(encoding="utf-8"))
            rep = (c.get("run") or {}).get("report") or {}
            loc = rep.get("location") or {}
            print(f"== {c['bug_id']}  정답 {(c.get('truth') or {}).get('file')}:{(c.get('truth') or {}).get('line')}"
                  f"  지목 {loc.get('file')}:{loc.get('line')}  보고 id {rep.get('fix_proposal_ids')}")
            print(f"   root_cause: {rep.get('root_cause')}")
            for p in (c.get("run") or {}).get("proposals", []):
                print(f"-- 제안 {p['id']}: {p['file']}:{p['line']}")
                print(p["diff"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
