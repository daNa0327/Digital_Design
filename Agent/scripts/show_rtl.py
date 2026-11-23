"""RTL Analyzer 5-1 결과를 표로 출력한다.

사용:
    python -m scripts.show_rtl dut/sync_fifo/rtl
    python -m scripts.show_rtl Manual_test/dut/some.v other.v
    python -m scripts.show_rtl dut/sync_fifo/rtl --json
"""

import argparse
import json
import sys
from pathlib import Path

from core.rtl_analyzer import parse_files


def _collect(args: list[str]) -> list[Path]:
    files: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            files += sorted(p.rglob("*.v")) + sorted(p.rglob("*.sv"))
        else:
            files.append(p)
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="파일 또는 폴더")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    a = ap.parse_args(argv)

    files = _collect(a.paths)
    if not files:
        print("Verilog 파일(.v/.sv)을 찾지 못했습니다.", file=sys.stderr)
        return 2
    mods = parse_files(files)
    if a.json:
        print(json.dumps([m.to_dict() for m in mods], ensure_ascii=False, indent=2))
        return 0

    for m in mods:
        print(f"\nmodule {m.name}  ({Path(m.path).name}:{m.line})")
        for p in m.params:
            kind = "localparam" if p.local else "parameter"
            val = "?" if p.value is None else p.value
            print(f"  {kind:<10} {p.name} = {p.default}  -> {val}")
        for p in m.ports:
            w = "?" if p.width is None else p.width
            rng = f"[{p.range_expr}]" if p.range_expr else ""
            reg = " reg" if p.is_reg else ""
            print(f"  {p.direction:<6}{reg:<4} {rng:<10} {p.name:<12} width={w}  (line {p.line})")
        for w in m.warnings:
            print(f"  WARN: {w}")
    print(f"\n모듈 {len(mods)}개, 파일 {len(files)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())