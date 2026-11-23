"""RTL Analyzer 5-1: Verilog 소스에서 모듈, 포트, 파라미터를 결정적으로 추출한다.

LLM을 쓰지 않는 경량 파서다 (주석 제거 -> 모듈 분리 -> 헤더 파싱).
지원 범위는 ANSI 스타일 포트 선언으로 한정하고, 범위 밖 구문은 추측하지 않고
`warnings`에 남긴다. (`core/analyzer.py`는 시뮬레이션 로그 판정용이라 이름이 다르다.)

공개 API:
    strip_comments(text) -> str            # 길이와 줄바꿈 보존 (오프셋/줄 번호 유지)
    parse_modules(text, path="") -> list[Module]
    parse_files(paths) -> list[Module]
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

DIRECTIONS = ("input", "output", "inout")
NET_TYPES = ("wire", "reg", "logic", "tri")


# ---------------------------------------------------------------- 데이터 모델
@dataclass
class Port:
    name: str
    direction: str                 # input | output | inout
    msb: int | None = None         # 숫자로 계산된 경우만
    lsb: int | None = None
    width: int | None = 1          # None = 폭을 숫자로 결정하지 못함
    range_expr: str | None = None  # 원문 "[7:0]" 안쪽 (없으면 None, 1비트)
    is_reg: bool = False
    signed: bool = False
    line: int = 0


@dataclass
class Param:
    name: str
    default: str                   # 원문 식
    value: int | None = None       # 정수로 계산된 경우만
    local: bool = False
    line: int = 0


@dataclass
class Module:
    name: str
    path: str = ""
    line: int = 0
    ports: list[Port] = field(default_factory=list)
    params: list[Param] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- 주석 제거
def strip_comments(text: str) -> str:
    """주석을 공백으로 바꾼다. 문자 수와 줄바꿈은 그대로라 오프셋이 유지된다."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        two = text[i:i + 2]
        if two == "//":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
        elif two == "/*":
            out.append("  ")
            i += 2
            while i < n and text[i:i + 2] != "*/":
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append("  ")
                i += 2
        elif c == '"':
            out.append(c)
            i += 1
            while i < n and text[i] != '"' and text[i] != "\n":
                if text[i] == "\\" and i + 1 < n:
                    out.append(text[i])
                    i += 1
                out.append(text[i])
                i += 1
            if i < n and text[i] == '"':
                out.append('"')
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


# ---------------------------------------------------------------- 보조 함수
def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _match_paren(text: str, open_idx: int) -> int:
    """text[open_idx]가 '('일 때 짝이 되는 ')'의 위치. 없으면 -1."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top(text: str, sep: str = ",") -> list[tuple[int, str]]:
    """괄호/대괄호/중괄호 밖의 sep으로 나눈다. (원문 내 시작 오프셋, 조각)."""
    parts: list[tuple[int, str]] = []
    depth, start = 0, 0
    for i, c in enumerate(text):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append((start, text[start:i]))
            start = i + 1
    parts.append((start, text[start:]))
    return parts


_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
           ast.LShift: operator.lshift, ast.RShift: operator.rshift}


def eval_const(expr: str, env: dict[str, int] | None = None) -> int | None:
    """정수 식(+ - * / % << >>, 괄호, 파라미터 이름)만 계산한다. 못 하면 None."""
    env = env or {}
    expr = expr.strip().replace("/", "//")
    expr = re.sub(r"\$clog2\s*\(", "_clog2(", expr)
    if not expr:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            raise ValueError(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_clog2" and len(node.args) == 1):
            v = ev(node.args[0])
            return max(0, (v - 1).bit_length()) if v > 0 else 0
        raise ValueError("unsupported")

    try:
        return ev(tree)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


_NUM_LIT = re.compile(r"^\s*(\d+)\s*'[sS]?[dD]\s*(\d+)\s*$")


def _const_value(expr: str, env: dict[str, int]) -> int | None:
    """파라미터 기본값 식을 정수로. 10진 리터럴 `8'd16`은 값 16으로 본다."""
    m = _NUM_LIT.match(expr)
    if m:
        return int(m.group(2))
    return eval_const(expr, env)


def _range(rng: str | None, env: dict[str, int]):
    """'7:0' -> (msb, lsb, width). 계산 못 하면 (None, None, None)."""
    if rng is None:
        return None, None, 1
    if ":" not in rng:
        return None, None, None
    left, right = rng.split(":", 1)
    msb, lsb = eval_const(left, env), eval_const(right, env)
    if msb is None or lsb is None:
        return msb, lsb, None
    return msb, lsb, abs(msb - lsb) + 1


# ---------------------------------------------------------------- 파라미터
_PARAM_KW = re.compile(r"^\s*(parameter|localparam)\b\s*", re.S)
_TYPE_PREFIX = re.compile(r"^(?:signed\s+|integer\s+|real\s+|unsigned\s+)*(?:\[[^\]]*\]\s*)?")


def _parse_param_items(chunk: str, base_offset: int, text: str, env: dict[str, int],
                       default_local: bool) -> list[Param]:
    """`parameter A = 1, B = 2` 형태의 쉼표 목록을 Param들로."""
    result: list[Param] = []
    local = default_local
    for off, piece in _split_top(chunk):
        s = piece
        m = _PARAM_KW.match(s)
        if m:
            local = m.group(1) == "localparam"
            s = s[m.end():]
        s = _TYPE_PREFIX.sub("", s.strip())
        if "=" not in s:
            continue
        name, expr = s.split("=", 1)
        name, expr = name.strip(), expr.strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            continue
        val = _const_value(expr, env)
        if val is not None:
            env[name] = val
        result.append(Param(name=name, default=expr, value=val, local=local,
                            line=_line_of(text, base_offset + off + max(0, len(piece) - len(piece.lstrip())))))
    return result


# ---------------------------------------------------------------- 포트
_DECL_HEAD = re.compile(
    r"^\s*(input|output|inout)\b\s*"
    r"(?:(wire|reg|logic|tri)\b\s*)?"
    r"(?:(signed)\b\s*)?"
    r"(?:\[\s*([^\]]*?)\s*\]\s*)?"
    r"(.*)$", re.S)


def _parse_ports(chunk: str, base_offset: int, text: str, env: dict[str, int],
                 warnings: list[str]) -> list[Port]:
    ports: list[Port] = []
    cur = None  # (direction, is_reg, signed, range)
    for off, piece in _split_top(chunk):
        if not piece.strip():
            continue
        lead = len(piece) - len(piece.lstrip())
        line = _line_of(text, base_offset + off + lead)
        m = _DECL_HEAD.match(piece)
        if m:
            direction, net, signed, rng, rest = m.groups()
            cur = (direction, net == "reg", bool(signed), rng)
            name = rest.strip()
        else:
            if cur is None:
                warnings.append(f"line {line}: 방향 없는 포트 '{piece.strip()}' (비ANSI 스타일?) - 건너뜀")
                continue
            name = piece.strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            warnings.append(f"line {line}: 해석하지 못한 포트 선언 '{piece.strip()}' - 건너뜀")
            continue
        direction, is_reg, signed, rng = cur
        msb, lsb, width = _range(rng, env)
        if rng is not None and width is None:
            warnings.append(f"line {line}: 포트 '{name}'의 폭 [{rng}]을 숫자로 계산하지 못함")
        ports.append(Port(name=name, direction=direction, msb=msb, lsb=lsb, width=width,
                          range_expr=rng, is_reg=is_reg, signed=signed, line=line))
    return ports


# ---------------------------------------------------------------- 모듈
_MODULE_START = re.compile(r"\b(?:module|macromodule)\s+([A-Za-z_]\w*)")
_BODY_PARAM = re.compile(r"\b(parameter|localparam)\b([^;]*);")


def parse_modules(text: str, path: str = "") -> list[Module]:
    """한 파일의 텍스트에서 모듈 목록을 뽑는다."""
    clean = strip_comments(text)
    modules: list[Module] = []
    pos = 0
    while True:
        m = _MODULE_START.search(clean, pos)
        if not m:
            break
        mod = Module(name=m.group(1), path=path, line=_line_of(clean, m.start()))
        i = m.end()
        env: dict[str, int] = {}

        # 헤더 파라미터  #( ... )
        j = _skip_ws(clean, i)
        if clean[j:j + 1] == "#":
            k = _skip_ws(clean, j + 1)
            if clean[k:k + 1] == "(":
                close = _match_paren(clean, k)
                if close < 0:
                    mod.warnings.append("파라미터 목록의 괄호가 닫히지 않음")
                    modules.append(mod)
                    break
                mod.params += _parse_param_items(clean[k + 1:close], k + 1, clean, env, False)
                i = close + 1

        # 포트 목록  ( ... );
        j = _skip_ws(clean, i)
        if clean[j:j + 1] == "(":
            close = _match_paren(clean, j)
            if close < 0:
                mod.warnings.append("포트 목록의 괄호가 닫히지 않음")
                modules.append(mod)
                break
            port_chunk_start, port_chunk = j + 1, clean[j + 1:close]
            i = close + 1
        else:
            port_chunk_start, port_chunk = j, ""

        end = clean.find("endmodule", i)
        body_end = end if end >= 0 else len(clean)
        if end < 0:
            mod.warnings.append("endmodule을 찾지 못함")
        body = clean[i:body_end]

        # 본문 파라미터 (포트보다 먼저 선언돼야 포트 폭에 쓸 수 있지만, 목록 순서대로 계산)
        for pm in _BODY_PARAM.finditer(body):
            chunk = pm.group(1) + " " + pm.group(2)
            mod.params += _parse_param_items(chunk, i + pm.start(), clean, env,
                                             pm.group(1) == "localparam")

        if port_chunk.strip():
            if re.search(r"\b(input|output|inout)\b", port_chunk):
                mod.ports = _parse_ports(port_chunk, port_chunk_start, clean, env, mod.warnings)
            else:
                mod.warnings.append("비ANSI 포트 선언은 지원하지 않음 - 포트를 추출하지 못함")
        if "`include" in clean[m.start():body_end] or "`define" in clean[m.start():body_end]:
            mod.warnings.append("매크로(`define/`include)는 해석하지 않음")
        if re.search(r"\bgenerate\b", body):
            mod.warnings.append("generate 블록은 해석하지 않음")

        modules.append(mod)
        pos = body_end + len("endmodule") if end >= 0 else len(clean)
    return modules


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def parse_files(paths: list[str | Path]) -> list[Module]:
    modules: list[Module] = []
    for p in paths:
        p = Path(p)
        modules += parse_modules(p.read_text(encoding="utf-8", errors="replace"), str(p))
    return modules