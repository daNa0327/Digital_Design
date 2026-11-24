"""Phase 7-1: Debug Agent가 쓰는 도구 모음 (결정적, LLM 없음).

원칙
- 모든 도구는 JSON 직렬화 가능한 dict를 반환한다. 오류도 예외가 아니라 {"error": ...}로 돌려줘서 LLM이 스스로 고치게 한다.
- 출력 길이는 상한을 두고, 잘렸으면 truncated와 이어서 읽을 위치를 알려 준다.
- Agent는 **논리 이름**(`rtl/fifo_ctrl.v`, `tb/tb_sync_fifo.v`)만 안다. 실제 경로(예: runs/.../B07/...)에는
  변형 ID 같은 정답 단서가 들어 있을 수 있어서 로그에서도 모두 논리 이름으로 바꾼다 (`sanitize_log`).
- `propose_fix`는 diff를 **저장만** 하고 파일을 쓰지 않는다. RTL만 대상이며 TB는 수정 제안을 받지 않는다
  ("테스트를 고쳐서 통과시키는" 행동 차단).
- 버그 카탈로그(정답지)는 이 모듈이 알지 못한다.

공개 API:
    DebugWorkspace(rtl, tb, log, vcd=None)             도구 본체
    workspace_from_files(rtl_files, tb_files, log, vcd_tools=None, path_roots=())
    sanitize_log(log, path_map) -> str
    tool_specs(ws) -> list[dict]
    dispatch_debug(ws, name, args) -> dict
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from core.rtl_analyzer import strip_comments
from core.vcd_tools import TOOL_SPECS as VCD_SPECS
from core.vcd_tools import VcdTools
from core.vcd_tools import dispatch as vcd_dispatch

MAX_LOG_LINES = 80
MAX_SRC_LINES = 120
MAX_SEARCH_RESULTS = 30
MAX_LINE_CHARS = 200
MAX_PROPOSALS = 5


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _lines(text: str) -> list[str]:
    """텍스트를 줄 목록으로. 끝의 줄바꿈이 만드는 가짜 빈 마지막 줄은 뺀다 (줄 수가 1 늘어나는 것을 막는다)."""
    ls = text.split("\n")
    if ls and ls[-1] == "":
        ls.pop()
    return ls


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _cut(s: str) -> str:
    return s if len(s) <= MAX_LINE_CHARS else s[:MAX_LINE_CHARS] + "...[줄 잘림]"


def _clamp(v: Any, lo: int, hi: int) -> int:
    return max(lo, min(int(v), hi))


# ---------------------------------------------------------------------------------------------
# 경로 정리: 로그에 섞인 절대 경로를 논리 이름으로 바꾼다
# ---------------------------------------------------------------------------------------------
_ABS_PATH = re.compile(r"""(?<![\w./\\-])(?:[A-Za-z]:[\\/]|/)(?:[^\s"'<>|:*?]+[\\/])*[^\s"'<>|:*?\\/]+\.(?:v|sv|vh|svh|log|vcd|tcl|f)\b""")


_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_DAYS = "Mon|Tue|Wed|Thu|Fri|Sat|Sun"
_WALLCLOCK = re.compile(rf"\b(?:{_DAYS}) (?:{_MONTHS}) +\d{{1,2}} \d{{2}}:\d{{2}}:\d{{2}} \d{{4}}\b")
_CPU_TIME = re.compile(r"Time \(s\): cpu = [^\n]*")


def sanitize_log(log: str, path_map: dict[str, str]) -> str:
    """로그에서 실행마다 달라지는 값(절대 경로, 시각, 경과 시간)을 지운다.

    경로는 논리 이름으로 바꾼다. 시각과 경과 시간은 `<time>`으로 바꾼다. 이걸 지우지 않으면 같은 실패를 다시 돌려도
    프롬프트가 달라져서 디스크 캐시가 맞지 않고 (호출 한도를 다시 씀) 재현도 안 된다.

    path_map: {파일 basename: 논리 이름}. basename이 맵에 있으면 논리 이름으로, 없으면 `<path>/basename`으로 바꾼다.
    경로 중간 폴더 이름(변형 ID, 평가 실행 폴더 등)이 Agent에게 전달되지 않게 하는 것이 목적이다.
    """
    def repl(m: re.Match) -> str:
        raw = m.group(0)
        base = PureWindowsPath(raw).name if ("\\" in raw or re.match(r"[A-Za-z]:", raw)) else PurePosixPath(raw).name
        return path_map.get(base, f"<path>/{base}")

    out = _ABS_PATH.sub(repl, _norm(log))
    out = _WALLCLOCK.sub("<time>", out)
    return _CPU_TIME.sub("Time (s): <elapsed>", out)


# ---------------------------------------------------------------------------------------------
# 수정 제안
# ---------------------------------------------------------------------------------------------
@dataclass
class Proposal:
    id: int
    file: str
    line: int                  # 수정이 실제로 처음 달라지는 줄 (1부터). find 블록의 첫 줄이 아니다
    find: str
    replace: str
    rationale: str
    diff: str

    def to_dict(self) -> dict:
        return asdict(self)


def _first_changed_line(text: str, idx: int, find: str, replace: str) -> int:
    """find가 text의 idx에서 시작할 때, replace와 처음 달라지는 문자가 있는 줄 번호(1부터).

    find 블록이 앞뒤 문맥을 길게 포함해도 변경 줄을 가리키게 한다. 블록의 첫 줄을 돌려주면
    Agent가 그 값을 보고서 위치로 베껴 실제 변경 줄과 어긋난다 (v0c B03).
    """
    d = 0
    n = min(len(find), len(replace))
    while d < n and find[d] == replace[d]:
        d += 1
    return text.count("\n", 0, idx + d) + 1


@dataclass
class DebugWorkspace:
    rtl: dict[str, str]                       # 논리 이름 -> 소스 텍스트 (예: "rtl/fifo_ctrl.v")
    tb: dict[str, str]                        # 논리 이름 -> 소스 텍스트 (예: "tb/tb_sync_fifo.v")
    log: str                                  # 이미 sanitize된 xsim 로그
    vcd: VcdTools | None = None
    proposals: list[Proposal] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rtl = {k: _norm(v) for k, v in self.rtl.items()}
        self.tb = {k: _norm(v) for k, v in self.tb.items()}
        self.log = _norm(self.log)
        self._log_lines = _lines(self.log)

    # ---- 파일 목록
    def list_files(self) -> dict[str, Any]:
        return {
            "rtl": [{"file": k, "lines": len(_lines(v))} for k, v in sorted(self.rtl.items())],
            "tb": [{"file": k, "lines": len(_lines(v))} for k, v in sorted(self.tb.items())],
            "log_lines": len(self._log_lines),
            "vcd": self.vcd is not None,
        }

    # ---- 로그
    def get_log_snippet(self, start_line: int = 1, max_lines: int = 60, pattern: str | None = None,
                        context: int = 0) -> dict[str, Any]:
        """로그 조회. pattern이 있으면 정규식에 일치하는 줄(앞뒤 context줄 포함), 없으면 start_line부터."""
        n_total = len(self._log_lines)
        cap = _clamp(max_lines, 1, MAX_LOG_LINES)
        if pattern:
            try:
                rx = re.compile(pattern, re.I)
            except re.error as e:
                return {"error": f"정규식 오류: {e}"}
            ctx = _clamp(context, 0, 5)
            hit = [i for i, ln in enumerate(self._log_lines, 1) if rx.search(ln)]
            keep: list[int] = []
            seen: set[int] = set()
            for i in hit:
                for j in range(max(1, i - ctx), min(n_total, i + ctx) + 1):
                    if j not in seen:
                        seen.add(j)
                        keep.append(j)
            shown = keep[:cap]
            out: dict[str, Any] = {
                "total_lines": n_total, "matches": len(hit), "returned": len(shown),
                "truncated": len(keep) > cap,
                "lines": [{"n": i, "text": _cut(self._log_lines[i - 1])} for i in shown]}
            if len(keep) > cap:
                out["next_start_line"] = keep[cap]
            return out
        start = max(1, int(start_line))
        if start > n_total:
            return {"error": f"start_line({start})이 로그 길이({n_total}줄)를 넘음", "total_lines": n_total}
        end = min(n_total, start + cap - 1)
        out = {"total_lines": n_total, "start_line": start, "returned": end - start + 1,
               "truncated": end < n_total,
               "lines": [{"n": i, "text": _cut(self._log_lines[i - 1])} for i in range(start, end + 1)]}
        if end < n_total:
            out["next_start_line"] = end + 1
        return out

    # ---- 소스
    def _read(self, files: dict[str, str], kind: str, file: str, start_line: int,
              end_line: int | None) -> dict[str, Any]:
        if file not in files:
            return {"error": f"{kind} 파일이 없음: {file}", "available": sorted(files)}
        lines = _lines(files[file])
        n = len(lines)
        start = max(1, int(start_line))
        if start > n:
            return {"error": f"start_line({start})이 파일 길이({n}줄)를 넘음", "total_lines": n}
        end = n if end_line is None else min(n, int(end_line))
        if end < start:
            return {"error": "end_line이 start_line보다 작음"}
        cap_end = min(end, start + MAX_SRC_LINES - 1)
        out: dict[str, Any] = {
            "file": file, "total_lines": n, "start_line": start, "end_line": cap_end,
            "truncated": cap_end < end,
            "lines": [{"n": i, "text": _cut(lines[i - 1])} for i in range(start, cap_end + 1)]}
        if cap_end < end:
            out["next_start_line"] = cap_end + 1
        return out

    def read_rtl(self, file: str, start_line: int = 1, end_line: int | None = None) -> dict[str, Any]:
        return self._read(self.rtl, "RTL", file, start_line, end_line)

    def read_tb(self, file: str, start_line: int = 1, end_line: int | None = None) -> dict[str, Any]:
        return self._read(self.tb, "TB", file, start_line, end_line)

    def search_rtl(self, pattern: str, max_results: int = 20) -> dict[str, Any]:
        """RTL 전체에서 정규식으로 줄을 찾는다 (신호가 어디서 쓰이는지 추적할 때)."""
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return {"error": f"정규식 오류: {e}"}
        cap = _clamp(max_results, 1, MAX_SEARCH_RESULTS)
        hits = []
        for f in sorted(self.rtl):
            for i, ln in enumerate(_lines(self.rtl[f]), 1):
                if rx.search(ln):
                    hits.append({"file": f, "n": i, "text": _cut(ln)})
        return {"matches": len(hits), "returned": min(len(hits), cap), "truncated": len(hits) > cap,
                "results": hits[:cap]}

    
    # ---- 수정 제안 (저장만, 적용 안 함)
    def propose_fix(self, file: str, find: str, replace: str, rationale: str = "") -> dict[str, Any]:
        if file in self.tb:
            return {"error": "TB 수정은 제안할 수 없음. 수정 대상은 RTL뿐이다. TB가 틀렸다고 판단하면 "
                             "final의 verdict를 tb_issue로 보고하라."}
        if file not in self.rtl:
            return {"error": f"RTL 파일이 없음: {file}", "available": sorted(self.rtl)}
        if not find:
            return {"error": "find가 비어 있음"}
        if find == replace:
            return {"error": "find와 replace가 같음"}
        text = self.rtl[file]
        count = text.count(find)
        if count == 0:
            return {"error": "find가 파일에 없음. read_rtl로 현재 텍스트를 다시 확인하라 (공백과 줄바꿈 포함 정확히 일치해야 함)"}
        if count > 1:
            return {"error": f"find가 {count}번 나타남. 한 번만 나타나도록 앞뒤 문맥을 포함해 길게 쓰라"}
        if _squash(strip_comments(text.replace(find, replace, 1))) == _squash(strip_comments(text)):
            return {"error": "수정이 주석이나 공백만 바꿔서 동작이 달라지지 않는다. 실제 RTL 코드를 바꾸는 수정안을 제안하라."}
        for p in self.proposals:
            if (p.file, p.find, p.replace) == (file, find, replace):
                return {"proposal_id": p.id, "diff": p.diff, "line": p.line, "duplicate": True}
        if len(self.proposals) >= MAX_PROPOSALS:
            return {"error": f"제안은 최대 {MAX_PROPOSALS}개"}
        idx = text.index(find)
        line = _first_changed_line(text, idx, find, replace)
        new_text = text[:idx] + replace + text[idx + len(find):]
        diff = "".join(difflib.unified_diff(text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                                            fromfile=f"a/{file}", tofile=f"b/{file}", n=2))
        p = Proposal(len(self.proposals) + 1, file, line, find, replace, rationale.strip(), diff)
        self.proposals.append(p)
        return {"proposal_id": p.id, "line": line, "diff": diff}


# ---------------------------------------------------------------------------------------------
# 작업 공간 만들기
# ---------------------------------------------------------------------------------------------
def workspace_from_files(rtl_files: list[str | Path], tb_files: list[str | Path], log: str,
                         vcd_tools: VcdTools | None = None) -> DebugWorkspace:
    """실제 파일에서 작업 공간을 만든다. 논리 이름은 `rtl/<파일명>`, `tb/<파일명>`.

    로그는 여기서 sanitize한다. 같은 basename의 파일이 둘 이상이면 모호해지므로 오류로 멈춘다.
    """
    rtl: dict[str, str] = {}
    tb: dict[str, str] = {}
    path_map: dict[str, str] = {}
    for kind, files, dst in (("rtl", rtl_files, rtl), ("tb", tb_files, tb)):
        for f in files:
            p = Path(f)
            logical = f"{kind}/{p.name}"
            if p.name in path_map:
                raise ValueError(f"같은 이름의 파일이 둘 이상: {p.name}")
            path_map[p.name] = logical
            dst[logical] = p.read_text(encoding="utf-8", errors="replace")
    return DebugWorkspace(rtl, tb, sanitize_log(log, path_map), vcd_tools)


# ---------------------------------------------------------------------------------------------
# 도구 명세와 디스패치
# ---------------------------------------------------------------------------------------------
_DEBUG_SPECS: list[dict[str, Any]] = [
    {"name": "get_log_snippet",
     "description": "시뮬레이션 로그 조회. pattern(정규식)이 있으면 일치하는 줄(앞뒤 context줄 포함), 없으면 start_line부터 max_lines줄. 전체 로그는 한 번에 주지 않는다.",
     "input_schema": {"type": "object", "properties": {
         "start_line": {"type": "integer"}, "max_lines": {"type": "integer"},
         "pattern": {"type": "string"}, "context": {"type": "integer"}}}},
    {"name": "read_rtl",
     "description": "RTL 파일의 줄 범위를 줄 번호와 함께 읽는다. 한 번에 최대 120줄.",
     "input_schema": {"type": "object", "required": ["file"], "properties": {
         "file": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}}},
    {"name": "read_tb",
     "description": "TB 파일의 줄 범위를 읽는다 (읽기 전용). 실패가 TB의 기대값 계산 오류인지 확인할 때 쓴다.",
     "input_schema": {"type": "object", "required": ["file"], "properties": {
         "file": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}}},
    {"name": "search_rtl",
     "description": "RTL 전체에서 정규식으로 줄을 찾는다. 신호가 어디서 대입되고 읽히는지 추적할 때 쓴다.",
     "input_schema": {"type": "object", "required": ["pattern"], "properties": {
         "pattern": {"type": "string"}, "max_results": {"type": "integer"}}}},
    {"name": "propose_fix",
     "description": "RTL 수정안을 저장한다 (파일은 바뀌지 않는다). find는 항상 **원본** 파일에서 정확히 한 번 나타나는 텍스트여야 한다 (이전 제안은 적용되지 않으므로 누적되지 않음). 주석이나 공백만 바꾸는 수정안은 거부된다. TB는 수정할 수 없다.",
     "input_schema": {"type": "object", "required": ["file", "find", "replace"], "properties": {
         "file": {"type": "string"}, "find": {"type": "string"}, "replace": {"type": "string"},
         "rationale": {"type": "string"}}}},
]


def tool_specs(ws: DebugWorkspace) -> list[dict[str, Any]]:
    """작업 공간에서 실제로 쓸 수 있는 도구 명세 (VCD가 없으면 VCD 도구는 뺀다)."""
    specs = list(_DEBUG_SPECS)
    if ws.vcd is not None:
        specs += VCD_SPECS
    return specs


def _coerce(value: Any, typ: str | None) -> Any:
    """LLM이 숫자를 문자열로 주는 경우를 고친다 ("10" -> 10). 못 고치면 원래 값을 돌려준다."""
    if typ == "integer" and isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return value
    if typ == "integer" and isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def dispatch_debug(ws: DebugWorkspace, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    """Agent의 도구 호출을 실행한다. 어떤 오류도 {"error": ...}로 돌려준다."""
    args = dict(args or {})
    specs = {s["name"]: s for s in tool_specs(ws)}
    if name not in specs:
        return {"error": f"알 수 없는 도구: {name}", "available": sorted(specs)}
    props = specs[name]["input_schema"].get("properties", {})
    for k, v in list(args.items()):
        if k in props:
            args[k] = _coerce(v, props[k].get("type"))
    missing = [k for k in specs[name]["input_schema"].get("required", []) if k not in args]
    if missing:
        return {"error": f"필수 인자가 없음: {missing}"}
    unknown = [k for k in args if k not in props]
    if unknown:
        return {"error": f"알 수 없는 인자: {unknown}", "allowed": sorted(props)}
    if name in {s["name"] for s in VCD_SPECS}:
        return vcd_dispatch(ws.vcd, name, args)
    try:
        return getattr(ws, name)(**args)
    except Exception as e:                      # 도구 내부 오류가 Agent 루프를 죽이지 않게
        return {"error": f"{type(e).__name__}: {e}"}