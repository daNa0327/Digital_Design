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

@dataclass
class XvlogInfo:
    attempted_files: list[str] = field(default_factory=list)  # 분석을 시작한 파일
    modules: list[str] = field(default_factory=list)
    errors: list[ErrorItem] = field(default_factory=list)

def parse_xvlog(text: str) -> XvlogInfo:
    info = XvlogInfo()
    info.attempted_files = [m.group("path") for m in _ANALYZING.finditer(text)]
    info.modules = [m.group("name") for m in _MODULE.finditer(text)]
    for i, m in enumerate(_ERROR.finditer(text)):
        line = m.group("line")
        info.errors.append(
            ErrorItem(
                stage="xvlog",
                code=m.group("code"),
                message=m.group("msg"),
                file=m.group("file"),
                line=int(line) if line else None,
                is_primary=(i == 0),      # 첫 에러가 주 원인, 나머지는 연쇄 에러
            )
        )
    return info