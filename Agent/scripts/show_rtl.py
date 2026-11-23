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

from core.rtl_analyzer import build_hierarchy, parse_files, render_tree


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
    h = build_hierarchy(mods)
    if a.json:
        print(json.dumps({"modules": [m.to_dict() for m in mods], "hierarchy": h.to_dict()},
                         ensure_ascii=False, indent=2))
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
        for i in m.instances:
            conns = len(i.connections)
            ov = f" #({', '.join(f'{k}={v}' for k, v in i.param_overrides.items())})" if i.param_overrides else ""
            print(f"  inst   {i.name}: {i.module}{ov}  ({conns} connections, line {i.line})")
        for w in m.warnings:
            print(f"  WARN: {w}")

    print("\n== hierarchy ==")
    print(f"top 후보: {h.top_candidates or '없음'}   best_top: {h.best_top}   testbench 추정: {h.testbench_like or '없음'}")
    tree = render_tree(h)
    if tree:
        print(tree)
    for w in h.warnings:
        print(f"WARN: {w}")
    bad = [i for i in h.issues if i["kind"] != "unconnected"]
    unconnected = [i for i in h.issues if i["kind"] == "unconnected"]
    for i in bad:
        print(f"ISSUE: {i['parent']}.{i['instance']} ({i['module']}): {i['kind']} {i['port']}")
    for i in unconnected:
        print(f"NOTE: {i['parent']}.{i['instance']} ({i['module']}): 연결되지 않은 포트 {i['port']}")
    print(f"\n모듈 {len(mods)}개, 파일 {len(files)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())