import re
from dataclasses import dataclass, field

from core.models import ErrorItem

_ANALYZING = re.compile(
    r'^INFO: \[VRFC 10-2263\] Analyzing \S+ file "(?P<path>[^"]+)"', re.M
)
_MODULE = re.compile(
    r"^INFO: \[VRFC 10-311\] analyzing module (?P<name>\S+)", re.M
)
_ERROR = re.compile(
    r"^ERROR: \[(?P<code>[^\]]+)\] (?P<msg>.*?)"
    r"(?: \[(?P<file>[^\]]+?):(?P<line>\d+)\])?[ \t\r]*$",
    re.M,
)

def _extract_errors(text: str, stage: str) -> list[ErrorItem]:
    # 에러 추출을 공통 함수
    errors: list[ErrorItem] = []
    for i, m in enumerate(_ERROR.finditer(text)):
        line = m.group("line")
        errors.append(
            ErrorItem(
                stage=stage,
                code=m.group("code"),
                message=m.group("msg"),
                file=m.group("file"),
                line=int(line) if line else None,
                is_primary=(i == 0),      # 같은 단계의 첫 에러가 주 원인
            )
        )
    return errors

# xvlog parser
@dataclass
class XvlogInfo:
    attempted_files: list[str] = field(default_factory=list)  # 분석을 시작한 파일
    modules: list[str] = field(default_factory=list)
    errors: list[ErrorItem] = field(default_factory=list)

def parse_xvlog(text: str) -> XvlogInfo:
    info = XvlogInfo()
    info.attempted_files = [m.group("path") for m in _ANALYZING.finditer(text)]
    info.modules = [m.group("name") for m in _MODULE.finditer(text)]
    info.errors = _extract_errors(text, "xvlog")
    return info

# xelab parser
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
    info.errors = _extract_errors(text, "xelab")
    return info