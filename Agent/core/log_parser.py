import re
from dataclasses import dataclass, field

from core.models import ErrorItem

# ---------------------------------------------------------------
# 공통: 시간 단위를 ps로 변환
# ---------------------------------------------------------------
_UNIT_PS = {
    "fs": 0.001,
    "ps": 1,
    "ns": 1_000,
    "us": 1_000_000,
    "ms": 1_000_000_000,
    "s": 1_000_000_000_000,
}

def time_to_ps(value: str, unit: str) -> int | None:
    factor = _UNIT_PS.get(unit)
    if factor is None:
        return None
    return round(float(value) * factor)


# ---------------------------------------------------------------
# 공통: "ERROR: [코드] 메시지 [파일:줄]" 형식 (xvlog / xelab / xsim 공통)
# ---------------------------------------------------------------
_ERROR = re.compile(
    r"^ERROR: \[(?P<code>[^\]]+)\] (?P<msg>.*?)"
    r"(?: \[(?P<file>[^\]]+?):(?P<line>\d+)\])?[ \t\r]*$",
    re.M,
)

def _scan_bracket_errors(text: str, stage: str) -> list[tuple[int, ErrorItem]]:
    found: list[tuple[int, ErrorItem]] = []
    for m in _ERROR.finditer(text):
        line = m.group("line")
        found.append((
            m.start(),
            ErrorItem(
                stage=stage,
                code=m.group("code"),
                message=m.group("msg"),
                file=m.group("file"),
                line=int(line) if line else None,
            ),
        ))
    return found

def _finalize(found: list[tuple[int, ErrorItem]]) -> list[ErrorItem]:
    """로그에 나온 순서로 정렬하고, 첫 에러만 주 원인으로 표시한다."""
    found.sort(key=lambda x: x[0])
    errors = [e for _, e in found]
    if errors:
        errors[0].is_primary = True
    return errors


# ---------------------------------------------------------------
# xvlog
# ---------------------------------------------------------------
_ANALYZING = re.compile(
    r'^INFO: \[VRFC 10-2263\] Analyzing \S+ file "(?P<path>[^"]+)"', re.M
)
_MODULE = re.compile(
    r"^INFO: \[VRFC 10-311\] analyzing module (?P<name>\S+)", re.M
)

@dataclass
class XvlogInfo:
    attempted_files: list[str] = field(default_factory=list)  # 분석을 시작한 파일
    modules: list[str] = field(default_factory=list)
    errors: list[ErrorItem] = field(default_factory=list)

def parse_xvlog(text: str) -> XvlogInfo:
    info = XvlogInfo()
    info.attempted_files = [m.group("path") for m in _ANALYZING.finditer(text)]
    info.modules = [m.group("name") for m in _MODULE.finditer(text)]
    info.errors = _finalize(_scan_bracket_errors(text, "xvlog"))
    return info


# ---------------------------------------------------------------
# xelab
# ---------------------------------------------------------------
_ELAB_MODULE = re.compile(r"^Compiling module work\.(?P<name>\S+)", re.M)
_SNAPSHOT = re.compile(r"^Built simulation snapshot (?P<name>\S+)", re.M)
_TIME_RES = re.compile(r"^Time Resolution for simulation is (?P<res>\S+)", re.M)

@dataclass
class XelabInfo:
    modules: list[str] = field(default_factory=list)   # 엘라보레이션 순서(말단 모듈부터)
    snapshot_built: bool = False
    snapshot_name: str | None = None
    time_resolution: str | None = None                 # 예: "1ps"
    errors: list[ErrorItem] = field(default_factory=list)

def parse_xelab(text: str) -> XelabInfo:
    info = XelabInfo()
    info.modules = [m.group("name") for m in _ELAB_MODULE.finditer(text)]
    m = _SNAPSHOT.search(text)
    if m:
        info.snapshot_built = True
        info.snapshot_name = m.group("name")
    m = _TIME_RES.search(text)
    if m:
        info.time_resolution = m.group("res")
    info.errors = _finalize(_scan_bracket_errors(text, "xelab"))
    return info


# ---------------------------------------------------------------
# xsim
# ---------------------------------------------------------------
# $finish 줄: $fatal로 끝났을 때는 " : File ... Line ..." 부분이 없다
_FINISH = re.compile(
    r"^\$finish called at time : (?P<t>\d+(?:\.\d+)?) (?P<unit>[a-z]+)"
    r'(?: : File "(?P<file>[^"]+)" Line (?P<line>\d+))?',
    re.M,
)

# TB가 $display로 출력하는 판정 마커 (줄 맨 앞에서만 인정)
_TB_MARKER = re.compile(
    r"^\[TB\] (?P<v>PASS|FAIL)(?:[: ]+(?P<rest>.*?))?[ \t\r]*$", re.M
)

# $error / $fatal 출력: "Error: 메시지" 다음 줄에 반드시 "Time: ..." 줄이 따라온다.
# Time 줄을 필수로 해서, TB가 $display("Error: ...")로 찍은 일반 출력과 구분한다.
_RT_ERROR = re.compile(
    r"^(?P<sev>Error|Fatal): (?P<msg>.*?)[ \t\r]*\r?\n"
    r"Time: (?P<t>\d+(?:\.\d+)?) (?P<unit>[a-z]+)\s+Iteration: \d+\s+"
    r"Process: \S+\s+Scope: \S+\s+File: (?P<file>.+?) Line: (?P<line>\d+)",
    re.M,
)

@dataclass
class XsimInfo:
    finish_time_ps: int | None = None      # 로그의 $finish 시각 (없으면 None)
    finish_file: str | None = None
    finish_line: int | None = None
    tb_markers: list[tuple[str, str]] = field(default_factory=list)  # (PASS|FAIL, 나머지 문구)
    errors: list[ErrorItem] = field(default_factory=list)

def parse_xsim(text: str) -> XsimInfo:
    info = XsimInfo()

    m = _FINISH.search(text)
    if m:
        info.finish_time_ps = time_to_ps(m.group("t"), m.group("unit"))
        info.finish_file = m.group("file")
        line = m.group("line")
        info.finish_line = int(line) if line else None

    info.tb_markers = [
        (m.group("v"), m.group("rest") or "") for m in _TB_MARKER.finditer(text)
    ]

    found = _scan_bracket_errors(text, "xsim")
    for m in _RT_ERROR.finditer(text):
        found.append((
            m.start(),
            ErrorItem(
                stage="xsim",
                code=None,
                message=m.group("msg"),
                file=m.group("file"),
                line=int(m.group("line")),
                severity="FATAL" if m.group("sev") == "Fatal" else "ERROR",
                time_ps=time_to_ps(m.group("t"), m.group("unit")),
            ),
        ))
    info.errors = _finalize(found)
    return info