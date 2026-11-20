"""LLM(Agent)에 노출할 VCD 조회 도구.

원칙
- 반환값은 항상 JSON 직렬화 가능한 dict. 오류도 예외가 아니라 {"error": ...}로 돌려줘서 LLM이 스스로 고치게 한다.
- 출력 길이는 상한을 두고, 잘렸으면 truncated=True와 이어서 읽을 시각(next_t0_ps)을 알려 준다.
- 값은 근거 없는 결론을 막도록 status, alias, 같은 이력 후보와 함께 반환한다.
"""

from __future__ import annotations

from typing import Any

from core.vcd_reader import VcdReader

MAX_LIST = 100
MAX_CHANGES = 200
MAX_ROWS = 100
MAX_SAMPLE_SIGNALS = 10


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(int(v), hi))


class VcdTools:
    def __init__(self, reader: VcdReader) -> None:
        self.r = reader

    # ---------- 값 표기 ----------
    def _fmt(self, value: str | None, fmt: str) -> str | None:
        if value is None or fmt == "bin" or len(value) == 1:
            return value
        n = VcdReader.to_int(value)
        if n is None:                       # x/z가 섞이면 이진 문자열 그대로
            return value
        return f"0x{n:x}" if fmt == "hex" else str(n)

    def _err(self, msg: str, name: str | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"error": msg}
        if name:
            leaf = name.rsplit(".", 1)[-1]
            out["suggestions"] = self.r.find(leaf)[:5]
        return out

    # ---------- 도구 ----------
    def list_signals(self, pattern: str | None = None, limit: int = 50) -> dict[str, Any]:
        """신호 이름 목록. pattern은 이름에 포함된 문자열 필터."""
        names = self.r.find(pattern) if pattern else self.r.names()
        limit = _clamp(limit, 1, MAX_LIST)
        shown = names[:limit]
        return {
            "total": len(names), "returned": len(shown), "truncated": len(names) > limit,
            "signals": [{"name": n, "width": self.r.info(n).width,
                         "aliases": len(self.r.aliases(n))} for n in shown],
        }

    def read_vcd_signal(self, name: str, t0_ps: int = 0, t1_ps: int | None = None,
                        max_changes: int = 50, fmt: str = "bin") -> dict[str, Any]:
        """신호의 [t0, t1] 구간 변화. 시작 시점 값을 첫 항목으로 포함한다."""
        if fmt not in ("bin", "hex", "dec"):
            return {"error": "fmt는 bin/hex/dec 중 하나"}
        if name not in self.r.names():
            return self._err(f"VCD에 없는 신호: {name}", name) | {
                "status": self.r.status(name)[0], "message": self.r.status(name)[1]}
        code, msg = self.r.status(name)
        if code == "not_loaded":
            return {"error": msg, "status": code}
        t1 = self.r.end_time_ps if t1_ps is None else t1_ps
        win = self.r.window(name, t0_ps, t1)
        cap = _clamp(max_changes, 1, MAX_CHANGES)
        shown = win[:cap]
        grp = self.r.net_group(name)
        out: dict[str, Any] = {
            "name": name, "width": self.r.info(name).width, "status": code,
            "window_ps": [t0_ps, t1], "total_in_window": len(win), "truncated": len(win) > cap,
            "changes": [{"t_ps": t, "value": self._fmt(v, fmt)} for t, v in shown],
            "aliases": grp["alias"], "same_history_candidates": grp["same_history"],
        }
        if msg:
            out["message"] = msg
        if len(win) > cap:
            out["next_t0_ps"] = win[cap][0]
        return out

    def sample_signals(self, clock: str, signals: list[str], t0_ps: int = 0,
                       t1_ps: int | None = None, max_rows: int = 40, when: str = "before",
                       edge: str = "rising", fmt: str = "bin") -> dict[str, Any]:
        """클럭 에지마다 신호값을 표로 샘플링 (기본: 에지 직전 값)."""
        if fmt not in ("bin", "hex", "dec"):
            return {"error": "fmt는 bin/hex/dec 중 하나"}
        if len(signals) > MAX_SAMPLE_SIGNALS:
            return {"error": f"signals는 최대 {MAX_SAMPLE_SIGNALS}개"}
        for n in [clock, *signals]:
            if n not in self.r.names():
                return self._err(f"VCD에 없는 신호: {n}", n)
            code, msg = self.r.status(n)
            if code == "not_loaded":
                return {"error": f"{n}: {msg}", "status": code}
        try:
            rows = self.r.sample_on_edge(clock, signals, t0_ps, t1_ps, edge, when)
        except ValueError as e:
            return {"error": str(e)}
        cap = _clamp(max_rows, 1, MAX_ROWS)
        out: dict[str, Any] = {
            "clock": clock, "edge": edge, "when": when, "total_edges": len(rows),
            "truncated": len(rows) > cap,
            "rows": [{"t_ps": t, "values": {k: self._fmt(v, fmt) for k, v in d.items()}}
                     for t, d in rows[:cap]],
        }
        if len(rows) > cap:
            out["next_t0_ps"] = rows[cap][0]
        return out


TOOL_SPECS = [
    {"name": "list_signals",
     "description": "VCD의 신호 이름 목록. pattern으로 이름 일부를 필터. 결과가 많으면 truncated=true.",
     "input_schema": {"type": "object", "properties": {
         "pattern": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "read_vcd_signal",
     "description": "신호의 시간 구간[t0_ps,t1_ps] 변화(시작 시점 값 포함). status, alias, 같은 이력 후보도 반환. "
                    "값이 x이거나 status가 ok가 아니면 alias와 교차 확인 전에 결론내지 말 것.",
     "input_schema": {"type": "object", "required": ["name"], "properties": {
         "name": {"type": "string"}, "t0_ps": {"type": "integer"}, "t1_ps": {"type": "integer"},
         "max_changes": {"type": "integer"}, "fmt": {"type": "string", "enum": ["bin", "hex", "dec"]}}}},
    {"name": "sample_signals",
     "description": "클럭 에지마다 여러 신호를 샘플링. 기본은 에지 직전 값(플립플롭이 읽는 값). "
                    "비동기 FIFO는 wr_ck/rd_ck로 도메인별로 따로 호출.",
     "input_schema": {"type": "object", "required": ["clock", "signals"], "properties": {
         "clock": {"type": "string"}, "signals": {"type": "array", "items": {"type": "string"}},
         "t0_ps": {"type": "integer"}, "t1_ps": {"type": "integer"}, "max_rows": {"type": "integer"},
         "when": {"type": "string", "enum": ["before", "after"]},
         "edge": {"type": "string", "enum": ["rising", "falling"]},
         "fmt": {"type": "string", "enum": ["bin", "hex", "dec"]}}}},
]


def dispatch(tools: VcdTools, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """LLM의 tool_use 호출을 실행한다. 어떤 오류도 {"error": ...}로 돌려준다."""
    if name not in {s["name"] for s in TOOL_SPECS}:
        return {"error": f"알 수 없는 도구: {name}", "available": [s["name"] for s in TOOL_SPECS]}
    try:
        return getattr(tools, name)(**args)
    except TypeError as e:
        return {"error": f"인자 오류: {e}"}
    except Exception as e:          # 도구 내부 오류가 Agent 루프를 죽이지 않게
        return {"error": f"{type(e).__name__}: {e}"}