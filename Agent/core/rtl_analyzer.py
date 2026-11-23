"""RTL Analyzer 5-1: Verilog 소스에서 모듈, 포트, 파라미터를 결정적으로 추출한다.

LLM을 쓰지 않는 경량 파서다 (주석 제거 -> 모듈 분리 -> 헤더 파싱).
지원 범위는 ANSI 스타일 포트 선언으로 한정하고, 범위 밖 구문은 추측하지 않고
`warnings`에 남긴다. (`core/analyzer.py`는 시뮬레이션 로그 판정용이라 이름이 다르다.)

5-2: 모듈 인스턴스와 계층(Hierarchy), top 모듈 추정, 포트 연결 점검.

공개 API:
    strip_comments(text) -> str            # 길이와 줄바꿈 보존 (오프셋/줄 번호 유지)
    parse_modules(text, path="") -> list[Module]
    parse_files(paths) -> list[Module]
    build_hierarchy(modules) -> Hierarchy  # top 후보, 자식 관계, 연결 점검
    render_tree(hierarchy, top=None) -> str
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
class Connection:
    port: str | None               # 이름 연결이면 포트 이름, 위치 연결이면 None
    expr: str                      # 연결된 식 (빈 문자열 = `.p()` 처럼 비워 둔 연결)
    positional: bool = False


@dataclass
class Instance:
    module: str                    # 인스턴스화한 모듈 이름
    name: str                      # 인스턴스 이름 (예: c1)
    line: int = 0
    connections: list[Connection] = field(default_factory=list)
    param_overrides: dict[str, str] = field(default_factory=dict)  # 이름 지정 #(.W(8))만


@dataclass
class Module:
    name: str
    path: str = ""
    line: int = 0
    ports: list[Port] = field(default_factory=list)
    params: list[Param] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)
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

        mod.instances = _parse_instances(body, i, clean, mod.warnings)

        modules.append(mod)
        pos = body_end + len("endmodule") if end >= 0 else len(clean)
    return modules


# ---------------------------------------------------------------- 인스턴스 (5-2)
_KEYWORDS = frozenset("""
always always_comb always_ff always_latch assign automatic begin case casex casez
default defparam deassign disable else end endcase endfunction endgenerate endmodule
endtask for force forever fork function generate genvar if initial inout input integer
join localparam module negedge output parameter posedge real realtime reg release repeat
signed specify task time tri unsigned wait wire logic while
and or nand nor xor xnor not buf bufif0 bufif1 notif0 notif1 nmos pmos cmos
pullup pulldown supply0 supply1 table endtable primitive endprimitive
""".split())

_IDENT = re.compile(r"[A-Za-z_]\w*")


def _read_instance_tail(text: str, j: int):
    """`type` 다음 위치 j에서 `[#(...)] name [[..]] ( ... )`를 읽는다.

    반환: (name, name_pos, conn_text, end_idx) 또는 None. #(...) 구간은 호출한 쪽이 읽는다.
    """
    k = _skip_ws(text, j)
    m = _IDENT.match(text, k)
    if not m or m.group(0) in _KEYWORDS:
        return None
    name, name_pos = m.group(0), k
    k = _skip_ws(text, m.end())
    if text[k:k + 1] == "[":
        close = text.find("]", k)
        if close < 0:
            return None
        k = _skip_ws(text, close + 1)
    if text[k:k + 1] != "(":
        return None
    close = _match_paren(text, k)
    if close < 0:
        return None
    return name, name_pos, text[k + 1:close], close + 1


def _parse_connections(chunk: str, warnings: list[str], where: str) -> list[Connection]:
    conns: list[Connection] = []
    if not chunk.strip():
        return conns
    for _, piece in _split_top(chunk):
        piece = piece.strip()
        if not piece:
            continue
        if piece == ".*":
            warnings.append(f"{where}: `.*` 와일드카드 연결은 해석하지 않음")
            continue
        m = re.match(r"^\.\s*([A-Za-z_]\w*)\s*(?:\((.*)\))?\s*$", piece, re.S)
        if m:
            conns.append(Connection(port=m.group(1), expr=(m.group(2) or "").strip()))
        else:
            conns.append(Connection(port=None, expr=piece, positional=True))
    return conns


def _parse_instances(body: str, body_offset: int, full: str, warnings: list[str]) -> list[Instance]:
    """본문에서 `모듈타입 인스턴스이름 ( ... );` 형태를 찾는다. 예약어와 게이트 프리미티브는 제외."""
    out: list[Instance] = []
    pos = 0
    while True:
        m = _IDENT.search(body, pos)
        if not m:
            break
        start = m.start()
        prev = body[start - 1] if start > 0 else " "
        word = m.group(0)
        if word in _KEYWORDS or prev in "$`." or prev.isalnum():
            pos = m.end()
            continue
        j = m.end()
        # 파라미터 오버라이드 #( ... )
        overrides: dict[str, str] = {}
        k = _skip_ws(body, j)
        if body[k:k + 1] == "#":
            k2 = _skip_ws(body, k + 1)
            if body[k2:k2 + 1] != "(":
                pos = m.end()
                continue
            close = _match_paren(body, k2)
            if close < 0:
                pos = m.end()
                continue
            for _, piece in _split_top(body[k2 + 1:close]):
                pm = re.match(r"^\s*\.\s*([A-Za-z_]\w*)\s*\((.*)\)\s*$", piece, re.S)
                if pm:
                    overrides[pm.group(1)] = pm.group(2).strip()
            j = close + 1
        parsed = False
        while True:
            tail = _read_instance_tail(body, j)
            if tail is None:
                break
            parsed = True
            name, name_pos, conn_text, end = tail
            line = _line_of(full, body_offset + name_pos)
            where = f"line {line}: {word} {name}"
            out.append(Instance(module=word, name=name, line=line,
                                connections=_parse_connections(conn_text, warnings, where),
                                param_overrides=dict(overrides)))
            j = _skip_ws(body, end)
            if body[j:j + 1] == ",":      # fifo a(...), b(...);
                j += 1
                continue
            break
        pos = j if parsed else m.end()
    return out


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


# ---------------------------------------------------------------- 계층 (5-2)
@dataclass
class Hierarchy:
    modules: dict[str, Module]                       # 이름 -> 모듈 (중복이면 먼저 나온 것)
    top_candidates: list[str]                        # 다른 모듈이 인스턴스화하지 않는 모듈 (testbench 제외)
    testbench_like: list[str]                        # 포트가 없고 다른 모듈을 인스턴스화하는 모듈 (testbench로 추정)
    best_top: str | None                             # 후보가 정확히 하나일 때만 값이 있음
    children: dict[str, list[str]]                   # 모듈 -> 자식 모듈 타입들 (등장 순서, 중복 제거)
    unresolved: list[tuple[str, str, str]]           # (부모, 인스턴스 이름, 알 수 없는 타입)
    issues: list[dict]                               # 연결 점검: unknown_port | unconnected | too_many_positional
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "top_candidates": self.top_candidates,
            "testbench_like": self.testbench_like,
            "best_top": self.best_top,
            "children": self.children,
            "unresolved": [list(u) for u in self.unresolved],
            "issues": self.issues,
            "warnings": self.warnings,
        }


def build_hierarchy(modules: list[Module]) -> Hierarchy:
    """모듈 목록에서 인스턴스 계층, top 후보, 포트 연결 문제를 계산한다."""
    warnings: list[str] = []
    by_name: dict[str, Module] = {}
    for m in modules:
        if m.name in by_name:
            warnings.append(f"모듈 '{m.name}'이(가) 중복 정의됨 ({by_name[m.name].path} / {m.path}) - 먼저 나온 것을 사용")
            continue
        by_name[m.name] = m

    children: dict[str, list[str]] = {}
    unresolved: list[tuple[str, str, str]] = []
    issues: list[dict] = []
    instantiated: set[str] = set()
    # testbench(포트 없음 + 인스턴스 있음)가 부르는 모듈은 "사용됨"으로 치지 않는다.
    # 그래야 RTL과 TB를 함께 줘도 DUT가 top 후보로 남는다.
    tb_like = [n for n, m in by_name.items() if not m.ports and m.instances]

    for m in by_name.values():
        kids: list[str] = []
        for inst in m.instances:
            child = by_name.get(inst.module)
            if child is None:
                unresolved.append((m.name, inst.name, inst.module))
                continue
            if m.name not in tb_like:
                instantiated.add(child.name)
            if child.name not in kids:
                kids.append(child.name)
            _check_connections(m, inst, child, issues)
        children[m.name] = kids

    tops = [n for n in by_name if n not in instantiated and n not in tb_like]

    best: str | None = None
    if len(tops) == 1:
        best = tops[0]
    elif len(tops) > 1:
        warnings.append(f"top 후보가 여러 개: {tops} - 하나를 지정해야 함")
    elif tb_like:
        warnings.append(f"RTL top이 없고 testbench로 보이는 모듈만 있음: {tb_like}")
    else:
        warnings.append("top 후보가 없음 (순환 인스턴스화일 수 있음)")

    for cyc in _find_cycles(children):
        warnings.append("순환 인스턴스화: " + " -> ".join(cyc))
    for parent, iname, typ in unresolved:
        warnings.append(f"{parent}.{iname}: 모듈 '{typ}' 정의를 찾지 못함 (라이브러리/IP/프리미티브?)")

    return Hierarchy(modules=by_name, top_candidates=tops, testbench_like=tb_like, best_top=best,
                     children=children, unresolved=unresolved, issues=issues, warnings=warnings)


def _check_connections(parent: Module, inst: Instance, child: Module, issues: list[dict]) -> None:
    """인스턴스의 연결을 자식 모듈의 포트와 대조한다."""
    port_names = [p.name for p in child.ports]
    connected: set[str] = set()
    for idx, c in enumerate(inst.connections):
        if c.positional:
            if idx < len(port_names):
                connected.add(port_names[idx])
            else:
                issues.append({"kind": "too_many_positional", "parent": parent.name,
                               "instance": inst.name, "module": child.name, "port": f"#{idx}"})
        elif c.port in port_names:
            if c.expr:                      # `.p()` 처럼 비운 연결은 미연결로 본다
                connected.add(c.port)
        else:
            issues.append({"kind": "unknown_port", "parent": parent.name,
                           "instance": inst.name, "module": child.name, "port": c.port})
    for name in port_names:
        if name not in connected:
            issues.append({"kind": "unconnected", "parent": parent.name,
                           "instance": inst.name, "module": child.name, "port": name})


def _find_cycles(children: dict[str, list[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    state: dict[str, int] = {}          # 1 = 방문 중, 2 = 완료

    def dfs(n: str, stack: list[str]) -> None:
        state[n] = 1
        for c in children.get(n, []):
            if state.get(c) == 1:
                cycles.append(stack[stack.index(c):] + [c] if c in stack else [n, c])
            elif state.get(c) is None:
                dfs(c, stack + [c])
        state[n] = 2

    for n in children:
        if state.get(n) is None:
            dfs(n, [n])
    return cycles


def render_tree(h: Hierarchy, top: str | None = None) -> str:
    """top에서 시작하는 인스턴스 트리를 텍스트로. top을 생략하면 best_top 또는 모든 후보."""
    roots = [top] if top else ([h.best_top] if h.best_top else list(h.top_candidates))
    lines: list[str] = []

    def walk(mod_name: str, prefix: str, label: str, path: tuple[str, ...]) -> None:
        lines.append(f"{prefix}{label}")
        mod = h.modules.get(mod_name)
        if mod is None or mod_name in path:
            return
        for idx, inst in enumerate(mod.instances):
            last = idx == len(mod.instances) - 1
            branch, cont = ("\u2514\u2500 ", "   ") if last else ("\u251c\u2500 ", "\u2502  ")
            child_prefix = prefix.replace("\u251c\u2500 ", "\u2502  ").replace("\u2514\u2500 ", "   ")
            known = inst.module in h.modules
            text = f"{inst.name}: {inst.module}" + ("" if known else "  (정의 없음)")
            if known and inst.module not in path + (mod_name,):
                walk(inst.module, child_prefix + branch, text, path + (mod_name,))
            else:
                lines.append(f"{child_prefix}{branch}{text}" + ("  (순환)" if known else ""))

    for r in roots:
        if r in h.modules:
            walk(r, "", r, ())
    return "\n".join(lines)