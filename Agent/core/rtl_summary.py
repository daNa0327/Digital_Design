"""RTL Analyzer 5-4: Analyzer 결과를 TB Generator(LLM)에 넘길 요약 dict로 묶고 검증한다.

요약의 모든 값은 소스에서 결정적으로 뽑은 것이다 (LLM이 추측한 값 없음).
LLM이 해야 할 일과 코드가 이미 알고 있는 사실을 분리하기 위한 경계 객체이며,
  - `blockers`  : 비어 있지 않으면 이 요약만으로는 TB를 만들 수 없다 (사람에게 되돌려야 함)
  - `notes`     : 막지는 않지만 TB 작성에 영향을 주는 사실 (클럭 없음, 리셋 없음 등)
  - `warnings`  : 분석 중 나온 경고 원문

공개 API:
    summarize_rtl(paths, top=None) -> dict
    summarize_modules(modules, top=None, sources=None) -> dict
    validate_summary(summary) -> list[str]      # 스키마 위반 목록 (비어 있으면 정상)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from core.rtl_analyzer import (Hierarchy, Module, build_hierarchy, parse_files,
                               top_interface)

SCHEMA_VERSION = 1


# ---------------------------------------------------------------- 생성
def summarize_rtl(paths: list[str | Path], top: str | None = None) -> dict:
    """파일 목록을 읽어 요약을 만든다. 파일 내용의 해시를 sources에 기록한다."""
    paths = [Path(p) for p in paths]
    sources = [{"path": p.as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:12]}
               for p in paths]
    return summarize_modules(parse_files(paths), top=top, sources=sources)


def summarize_modules(modules: list[Module], top: str | None = None,
                      sources: list[dict] | None = None) -> dict:
    h = build_hierarchy(modules)
    chosen = top or h.best_top
    blockers: list[str] = []
    notes: list[str] = []

    if chosen is None or chosen not in h.modules:
        if top:
            blockers.append(f"지정한 top '{top}' 모듈을 찾지 못함")
        elif h.top_candidates:
            blockers.append(f"top 모듈을 정하지 못함 (후보: {h.top_candidates})")
        else:
            blockers.append("top 모듈을 정하지 못함 (후보 없음)")
        return _skeleton(h, sources, blockers, notes)

    mod = h.modules[chosen]
    iface = top_interface(h, chosen) or {"clocks": [], "resets": [], "multi_clock": False,
                                        "timescale": h.timescale_status}
    closure = _closure(h, chosen)

    # ---- top 포트와 구동/관측 대상
    ports = [{"name": p.name, "direction": p.direction, "width": p.width, "range_expr": p.range_expr}
             for p in mod.ports]
    clock_ports = {c["port"] for c in iface["clocks"]}
    reset_ports = {r["port"] for r in iface["resets"]}
    inputs = [p["name"] for p in ports
              if p["direction"] in ("input", "inout") and p["name"] not in clock_ports | reset_ports]
    outputs = [p["name"] for p in ports if p["direction"] in ("output", "inout")]

    # ---- timescale: 설계 기준 상태와 TB에 쓸 지시문
    top_ts = mod.timescale
    status = h.timescale_status
    if status == "all":
        tb_directive = f"`timescale {top_ts}"
        if len({h.timescale_by_module[n] for n in closure}) > 1:
            notes.append("모듈마다 timescale 값이 다름 - TB는 top의 값을 따름")
    elif status == "none":
        tb_directive = ""
    else:
        tb_directive = None
        missing = [n for n in closure if h.timescale_by_module.get(n) is None]
        blockers.append(f"timescale이 일부 모듈에만 있음 (없는 모듈: {missing}) - "
                        "TB에 어떤 값을 써도 xelab에서 실패하므로 RTL 수정 또는 xelab 기본 timescale 옵션이 필요")

    # ---- 차단 사유
    for p in ports:
        if p["width"] is None:
            blockers.append(f"top 포트 '{p['name']}'의 폭을 계산하지 못함 ([{p['range_expr']}])")
    if any("비ANSI" in w for w in mod.warnings):
        blockers.append("top 모듈의 포트를 추출하지 못함 (비ANSI 포트 선언)")
    for parent, inst, typ in h.unresolved:
        if parent in closure:
            blockers.append(f"{parent}.{inst}: 모듈 '{typ}' 정의가 없음 (시뮬레이션 불가)")
    for i in h.issues:
        if i["kind"] in ("unknown_port", "too_many_positional") and i["parent"] in closure:
            blockers.append(f"{i['parent']}.{i['instance']} ({i['module']}): 포트 연결 오류 {i['kind']} {i['port']}")

    # ---- 참고 사항 (TB 작성에 영향, 차단하지 않음)
    if not iface["clocks"]:
        notes.append("클럭을 찾지 못함 - 조합 회로로 취급하거나 클럭 포트가 없는 설계")
    if not iface["resets"]:
        notes.append("리셋을 찾지 못함 - TB에서 리셋 없이 초기화해야 함")
    if iface["multi_clock"]:
        notes.append("클럭이 2개 이상 - TB에서 클럭마다 독립된 생성이 필요 (CDC 설계)")
    for r in iface["resets"]:
        if r["evidence"] != "sensitivity+if":
            notes.append(f"리셋 '{r['port']}' 판별 근거가 약함 ({r['evidence']})")

    warnings = [f"{n}: {w}" for n in closure for w in h.modules[n].warnings] + list(h.warnings)

    return {
        "schema_version": SCHEMA_VERSION,
        "top": chosen,
        "sources": sources or [],
        "ports": ports,
        "inputs_to_drive": inputs,
        "outputs_to_observe": outputs,
        "parameters": [{"name": p.name, "default": p.default, "value": p.value, "local": p.local}
                       for p in mod.params],
        "clocks": iface["clocks"],
        "resets": iface["resets"],
        "multi_clock": iface["multi_clock"],
        "timescale": {"status": status, "value": top_ts, "tb_directive": tb_directive},
        "hierarchy": _tree(h, chosen, None, ()),
        "modules": {n: _module_brief(h.modules[n]) for n in closure},
        "ready_for_tb": not blockers,
        "blockers": blockers,
        "notes": notes,
        "warnings": warnings,
    }


def _skeleton(h: Hierarchy, sources, blockers, notes) -> dict:
    """top을 정하지 못했을 때의 요약. 스키마는 그대로 두고 값은 비운다."""
    return {
        "schema_version": SCHEMA_VERSION, "top": None, "sources": sources or [],
        "ports": [], "inputs_to_drive": [], "outputs_to_observe": [], "parameters": [],
        "clocks": [], "resets": [], "multi_clock": False,
        "timescale": {"status": h.timescale_status, "value": None, "tb_directive": None},
        "hierarchy": None, "modules": {},
        "ready_for_tb": False, "blockers": blockers, "notes": notes, "warnings": list(h.warnings),
    }


def _closure(h: Hierarchy, top: str) -> list[str]:
    seen: list[str] = []
    stack = [top]
    while stack:
        n = stack.pop(0)
        if n not in seen and n in h.modules:
            seen.append(n)
            stack += h.children.get(n, [])
    return seen


def _module_brief(m: Module) -> dict:
    return {
        "file": Path(m.path).name if m.path else "",
        "ports": [{"name": p.name, "direction": p.direction, "width": p.width} for p in m.ports],
        "instances": [{"name": i.name, "module": i.module} for i in m.instances],
        "clocks": sorted({c.name for c in m.clocks}),
        "resets": sorted({r.name for r in m.resets}),
    }


def _tree(h: Hierarchy, name: str, inst: str | None, path: tuple[str, ...]) -> dict:
    node: dict = {"module": name, "instance": inst, "children": []}
    mod = h.modules.get(name)
    if mod is None:
        node["defined"] = False
        return node
    if name in path:
        node["cycle"] = True
        return node
    for i in mod.instances:
        node["children"].append(_tree(h, i.module, i.name, path + (name,)))
    return node


# ---------------------------------------------------------------- 검증
_TOP_KEYS = {
    "schema_version": int, "top": (str, type(None)), "sources": list, "ports": list,
    "inputs_to_drive": list, "outputs_to_observe": list, "parameters": list, "clocks": list,
    "resets": list, "multi_clock": bool, "timescale": dict, "hierarchy": (dict, type(None)),
    "modules": dict, "ready_for_tb": bool, "blockers": list, "notes": list, "warnings": list,
}


def validate_summary(s: dict) -> list[str]:
    """요약 dict가 스키마를 지키는지 검사한다. 위반 사항 목록을 돌려준다 (비어 있으면 정상)."""
    errs: list[str] = []
    if not isinstance(s, dict):
        return ["요약이 dict가 아님"]
    for key, typ in _TOP_KEYS.items():
        if key not in s:
            errs.append(f"키 누락: {key}")
        elif not isinstance(s[key], typ) or (typ is int and isinstance(s[key], bool)):
            errs.append(f"키 '{key}'의 타입이 잘못됨: {type(s[key]).__name__}")
    for extra in set(s) - set(_TOP_KEYS):
        errs.append(f"알 수 없는 키: {extra}")
    if errs:
        return errs
    if s["schema_version"] != SCHEMA_VERSION:
        errs.append(f"schema_version 불일치: {s['schema_version']} != {SCHEMA_VERSION}")
    for i, p in enumerate(s["ports"]):
        if not (isinstance(p, dict) and isinstance(p.get("name"), str)
                and p.get("direction") in ("input", "output", "inout")
                and (p.get("width") is None or isinstance(p.get("width"), int))):
            errs.append(f"ports[{i}] 형식 오류: {p}")
    names = {p.get("name") for p in s["ports"] if isinstance(p, dict)}
    for key in ("inputs_to_drive", "outputs_to_observe"):
        for n in s[key]:
            if n not in names:
                errs.append(f"{key}에 포트 목록에 없는 이름: {n}")
    for c in s["clocks"]:
        if c.get("port") not in names:
            errs.append(f"클럭 '{c.get('port')}'이(가) top 포트가 아님")
    for r in s["resets"]:
        if r.get("port") not in names:
            errs.append(f"리셋 '{r.get('port')}'이(가) top 포트가 아님")
    ts = s["timescale"]
    if set(ts) != {"status", "value", "tb_directive"} or ts["status"] not in ("none", "all", "mixed"):
        errs.append(f"timescale 형식 오류: {ts}")
    if s["ready_for_tb"] != (not s["blockers"]):
        errs.append("ready_for_tb와 blockers가 일치하지 않음")
    if s["top"] is not None and s["top"] not in s["modules"]:
        errs.append("top이 modules에 없음")
    if s["top"] is None and s["ready_for_tb"]:
        errs.append("top이 없는데 ready_for_tb가 True")
    return errs