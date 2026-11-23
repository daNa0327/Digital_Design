"""RTL Analyzer 5-3: always 블록의 감도 목록으로 클럭과 리셋을 판별한다.

판별 근거를 `evidence`로 남긴다 (구조적 근거가 이름 휴리스틱보다 강하다).
  sensitivity+if   : 감도 목록의 에지 신호가 블록의 첫 if 조건에서도 검사됨 (비동기 리셋, 가장 강함)
  sensitivity+name : 감도 목록에 에지 신호가 둘이고 이름만으로 리셋을 골랐음
  if+name          : 에지가 하나인 블록의 첫 if가 리셋 이름 신호를 검사함 (동기 리셋)

모호하면 분류하지 않고 경고를 남긴다. 조합 논리(`always @*`, 레벨 감도)는 무시한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

RESET_NAME = re.compile(r"(rst|reset|clr|clear)", re.I)
_ALWAYS = re.compile(r"\balways(?:_ff|_latch|_comb)?\b\s*@")
_EDGE_ITEM = re.compile(r"^\s*(posedge|negedge)\s+([A-Za-z_]\w*)")
_IDENT = re.compile(r"[A-Za-z_]\w*")
_LOW_CMP = re.compile(r"(==|===)\s*(1'b0|0)\b")


@dataclass
class ClockSig:
    name: str
    edge: str                      # posedge | negedge
    uses: int = 1                  # 이 신호를 클럭으로 쓰는 always 블록 수
    lines: list[int] = field(default_factory=list)


@dataclass
class ResetSig:
    name: str
    active_high: bool | None       # None = 극성을 알 수 없음
    asynchronous: bool
    evidence: str
    uses: int = 1
    lines: list[int] = field(default_factory=list)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _match_paren(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _first_if_condition(text: str, i: int) -> str | None:
    """always 헤더 뒤(i)에서 블록의 첫 문장이 `if (cond)`이면 cond를 돌려준다."""
    k = _skip_ws(text, i)
    m = re.match(r"begin\b(?:\s*:\s*\w+)?", text[k:])
    if m:
        k = _skip_ws(text, k + m.end())
    m = re.match(r"if\s*\(", text[k:])
    if not m:
        return None
    open_idx = k + m.end() - 1
    close = _match_paren(text, open_idx)
    return text[open_idx + 1:close] if close >= 0 else None


def _cond_signals(cond: str | None) -> set[str]:
    return set(_IDENT.findall(re.sub(r"\d+\s*'[sS]?[bBdDhHoO]\s*[0-9a-fA-FxXzZ_]+", " ", cond))) if cond else set()


def _cond_negated(cond: str | None) -> bool | None:
    """조건이 `!x`, `~x`, `x == 0`이면 True, `x`, `x == 1`이면 False. 단순 조건이 아니면 None."""
    if cond is None or len(_cond_signals(cond)) != 1:
        return None
    c = cond.strip()
    if c.startswith(("!", "~")) or _LOW_CMP.search(c):
        return True
    return False


def extract_clk_rst(text: str, start: int, end: int, port_names: set[str],
                    warnings: list[str]) -> tuple[list[ClockSig], list[ResetSig]]:
    """text[start:end] 구간의 always 블록에서 클럭과 리셋을 뽑는다 (text는 주석이 제거된 것)."""
    clocks: dict[tuple[str, str], ClockSig] = {}
    resets: dict[str, ResetSig] = {}

    def add_clock(name: str, edge: str, line: int) -> None:
        c = clocks.setdefault((name, edge), ClockSig(name, edge, 0))
        c.uses += 1
        c.lines.append(line)

    def add_reset(name: str, active_high: bool | None, asynchronous: bool, evidence: str, line: int) -> None:
        r = resets.get(name)
        if r is None:
            r = resets[name] = ResetSig(name, active_high, asynchronous, evidence, 0)
        elif (r.active_high, r.asynchronous) != (active_high, asynchronous):
            warnings.append(f"line {line}: 리셋 '{name}'이(가) 블록마다 다르게 쓰임 (극성/동기성 불일치)")
        r.uses += 1
        r.lines.append(line)

    pos = start
    while True:
        m = _ALWAYS.search(text, pos, end)
        if not m:
            break
        pos = m.end()
        k = _skip_ws(text, m.end())
        if text[k:k + 1] != "(":
            continue                                  # always @* 등
        close = _match_paren(text, k)
        if close < 0:
            continue
        sens = text[k + 1:close]
        line = _line_of(text, m.start())
        if "*" in sens:
            continue
        edges: list[tuple[str, str]] = []
        level = False
        for item in re.split(r"\bor\b|,", sens):
            if not item.strip():
                continue
            em = _EDGE_ITEM.match(item)
            if em:
                edges.append((em.group(1), em.group(2)))
            else:
                level = True
        if level or not edges:
            continue                                  # 조합 논리

        cond = _first_if_condition(text, close + 1)
        in_cond = _cond_signals(cond)
        negated = _cond_negated(cond)

        if len(edges) == 1:
            edge, sig = edges[0]
            add_clock(sig, edge, line)
            if len(in_cond) == 1:
                (r,) = in_cond
                if r != sig and RESET_NAME.search(r):
                    add_reset(r, None if negated is None else not negated, False, "if+name", line)
        elif len(edges) == 2:
            by_cond = [i for i, (_, s) in enumerate(edges) if s in in_cond]
            by_name = [i for i, (_, s) in enumerate(edges) if RESET_NAME.search(s)]
            if len(by_cond) == 1:
                ridx, evidence = by_cond[0], "sensitivity+if"
            elif len(by_name) == 1:
                ridx, evidence = by_name[0], "sensitivity+name"
            else:
                warnings.append(f"line {line}: 감도 목록 '{sens.strip()}'에서 클럭/리셋을 구분하지 못함")
                continue
            redge, rsig = edges[ridx]
            cedge, csig = edges[1 - ridx]
            active_high = redge == "posedge"
            if negated is not None and negated == active_high:
                warnings.append(f"line {line}: 리셋 '{rsig}'의 에지({redge})와 if 조건의 극성이 맞지 않음")
            add_clock(csig, cedge, line)
            add_reset(rsig, active_high, True, evidence, line)
        else:
            warnings.append(f"line {line}: 에지 신호가 3개 이상인 감도 목록은 해석하지 않음")

    for name in sorted({c.name for c in clocks.values()} | set(resets)):
        if name not in port_names:
            warnings.append(f"클럭/리셋 '{name}'이(가) 포트가 아님 (내부 생성 신호?)")
    return list(clocks.values()), list(resets.values())