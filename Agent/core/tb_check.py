"""TB Generator 6-2: LLM이 만든 TB를 컴파일 전에 정적으로 검사한다 (결정적, LLM 호출 없음).

LLM의 출력은 믿지 않는다. 이 검사기는 "시뮬레이터를 돌려 볼 가치가 있는 TB인가"만 거른다.
  - error  : 이 TB로는 평가가 성립하지 않는다 (규약 위반, timescale 충돌, 미구동 입력 ...)
  - warning: 돌려는 볼 수 있지만 검증 품질이 의심된다 (워치독 없음, `!==` 없음 ...)
컴파일이 되는지, 골든이 PASS하는지는 여기서 판단하지 않는다 (6-3 Compile Gate, 6-4 평가).

공개 API:
    extract_verilog(text) -> (code, problems)       # LLM 응답에서 Verilog 코드만 꺼냄
    check_tb(code, summary) -> list[Issue]
    errors_of(issues) / has_errors(issues)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.rtl_analyzer import strip_comments


@dataclass(frozen=True)
class Issue:
    level: str          # "error" | "warning"
    code: str           # 짧은 식별자 (테스트와 재시도 피드백에서 사용)
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}"


def errors_of(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.level == "error"]


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)


# ---------------------------------------------------------------- 응답에서 코드 추출
_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\n(.*?)```", re.S)


def extract_verilog(text: str) -> tuple[str, list[str]]:
    """응답 텍스트에서 TB 코드를 꺼낸다. (코드, 문제 목록)을 돌려준다. 코드가 없으면 ""를 돌려준다.

    1) ``` 펜스 블록 중 `module`을 포함하는 가장 긴 것
    2) 펜스가 없으면 첫 `module`(또는 그 앞의 `timescale 줄)부터 마지막 `endmodule`까지
    LLM이 코드 바깥에 설명을 붙이거나 블록을 여러 개 내도 코드만 얻고, 그 사실은 문제로 알린다.
    """
    problems: list[str] = []
    blocks = [m.group(2) for m in _FENCE.finditer(text) if re.search(r"\bmodule\b", m.group(2))]
    if blocks:
        if len(blocks) > 1:
            problems.append(f"module을 포함한 코드 블록이 {len(blocks)}개 - 가장 긴 것을 사용")
        code = max(blocks, key=len)
    else:
        m = re.search(r"(?m)^(?:[ \t]*`timescale[^\n]*\n)?[ \t]*module\b", text)
        end = text.rfind("endmodule")
        if not m or end < m.start():
            return "", ["응답에서 module ... endmodule 코드를 찾지 못함"]
        code = text[m.start(): end + len("endmodule")]
        problems.append("코드 펜스(```) 없이 응답함 - 첫 module부터 마지막 endmodule까지를 사용")
    return code.strip() + "\n", problems


# ---------------------------------------------------------------- 파싱 보조
_MODULE = re.compile(r"\bmodule\s+(\w+)\s*(#\s*\(.*?\)\s*)?(\(.*?\))?\s*;", re.S)
_SV_ONLY = [
    (r"\blogic\b", "logic"), (r"\balways_ff\b", "always_ff"), (r"\balways_comb\b", "always_comb"),
    (r"\balways_latch\b", "always_latch"), (r"\bclass\b", "class"), (r"\binterface\b", "interface"),
    (r"\bprogram\b", "program"), (r"\bint\b", "int"), (r"\bbit\b", "bit"),
    (r"\bstring\b", "string"), (r"\bassert\b", "assert"), (r"\$urandom\w*", "$urandom"),
    (r"\bforeach\b", "foreach"), (r"\bfunction\s+automatic\b", "function automatic"),
]


def _string_literals(code: str) -> list[str]:
    return re.findall(r'"((?:[^"\\\n]|\\.)*)"', code)


def _norm_ts(s: str) -> str:
    return re.sub(r"\s+", "", s.replace("`timescale", ""))


def _instantiations(body: str, module: str) -> list[tuple[str, str]]:
    """`module inst ( ... );` 형태의 인스턴스를 (이름, 연결 문자열)로 돌려준다 (괄호 균형 기준)."""
    out = []
    for m in re.finditer(rf"\b{re.escape(module)}\b\s*(?:#\s*\(.*?\)\s*)?(\w+)\s*\(", body, re.S):
        depth, i = 1, m.end()
        while i < len(body) and depth:
            depth += {"(": 1, ")": -1}.get(body[i], 0)
            i += 1
        out.append((m.group(1), body[m.end(): i - 1]))
    return out


def _named_connections(conn: str) -> dict[str, str] | None:
    """`.port(expr)` 목록을 {port: expr}로. 위치 기반 연결이면 None."""
    if not conn.strip():
        return {}
    if not re.match(r"\s*\.", conn):
        return None
    res, i = {}, 0
    for m in re.finditer(r"\.\s*(\w+)\s*\(", conn):
        if m.start() < i:
            continue
        depth, j = 1, m.end()
        while j < len(conn) and depth:
            depth += {"(": 1, ")": -1}.get(conn[j], 0)
            j += 1
        res[m.group(1)] = conn[m.end(): j - 1].strip()
        i = j
    return res


def _base_ident(expr: str) -> str | None:
    """연결식이 신호 하나(비트/파트 선택 포함)면 그 이름. 상수나 연결 없음이면 None."""
    m = re.fullmatch(r"\s*(\w+)\s*(\[[^\]]*\]\s*)*", expr)
    if m and not re.fullmatch(r"\d+", m.group(1)):
        return m.group(1)
    return None


def _assigned(code: str, name: str) -> bool:
    """name이 TB 어딘가에서 값을 받는지 (=, <=, 비트/파트 선택 포함, 연결 {a,b}는 보지 않음)."""
    return bool(re.search(rf"(?<![\w.]){re.escape(name)}\s*(\[[^\]]*\]\s*)*(<=|=)(?!=)", code))


# ---------------------------------------------------------------- 검사
def check_tb(code: str, summary: dict) -> list[Issue]:
    """TB 코드를 요약(summary)에 비추어 검사한다. error가 하나라도 있으면 시뮬레이션하지 않는다."""
    issues: list[Issue] = []
    E = lambda c, m: issues.append(Issue("error", c, m))      # noqa: E731
    W = lambda c, m: issues.append(Issue("warning", c, m))    # noqa: E731

    if not code.strip():
        return [Issue("error", "no_code", "TB 코드가 비어 있음")]
    src = strip_comments(code)
    top = summary["top"]

    # --- 모듈 구조: TB는 포트 없는 모듈 하나
    mods = list(_MODULE.finditer(src))
    if not mods:
        return [Issue("error", "no_module", "module 선언을 찾지 못함")]
    if len(re.findall(r"\bendmodule\b", src)) != len(mods):
        E("unbalanced_module", "module과 endmodule의 개수가 다름 (출력이 잘렸을 수 있음)")
    if len(mods) > 1:
        E("multiple_modules", f"TB 파일에 module이 {len(mods)}개 ({[m.group(1) for m in mods]}) - 하나만 허용")
    tb = mods[0]
    tb_name = tb.group(1)
    if tb.group(3) and tb.group(3).strip("() \n\t"):
        E("tb_has_ports", f"TB 모듈 '{tb_name}'에 포트가 있음 - 최상위 TB는 포트가 없어야 함")
    if tb_name == top:
        E("tb_name_clash", f"TB 모듈 이름이 DUT top('{top}')과 같음")
    body = src[tb.end():]

    # --- 문법 범위: Verilog-2001만 (xvlog를 Verilog 모드로 돌림)
    bad = sorted({label for pat, label in _SV_ONLY if re.search(pat, _strip_strings(src))})
    if bad:
        E("systemverilog_construct", f"SystemVerilog 전용 구문 사용: {bad} (v1은 Verilog만 지원)")

    # --- timescale: 설계 상태에 맞아야 xelab이 통과한다 (XSIM 43-4099)
    directive = summary["timescale"]["tb_directive"]
    ts_found = re.findall(r"`timescale[ \t]+([^\n]+)", src)
    if directive == "":
        if ts_found:
            E("timescale_forbidden", "RTL에 timescale이 없는데 TB에 `timescale을 씀 - xelab에서 XSIM 43-4099로 실패함")
    elif directive:
        want = _norm_ts(directive)
        if not ts_found:
            E("timescale_missing", f"RTL 전체에 timescale이 있는데 TB에 없음 - `{directive[1:]}` 필요")
        elif _norm_ts(ts_found[0]) != want:
            E("timescale_mismatch", f"TB timescale '{ts_found[0].strip()}'이 RTL('{want}')과 다름")

    # --- DUT 인스턴스와 포트 연결 (이름 기반, 빠짐/초과 없음)
    insts = _instantiations(body, top)
    ports = [p["name"] for p in summary["ports"]]
    conns: dict[str, str] = {}
    if not insts:
        E("dut_not_instantiated", f"DUT '{top}'을 인스턴스화하지 않음")
    else:
        if len(insts) > 1:
            W("dut_multiple_instances", f"DUT 인스턴스가 {len(insts)}개 - 첫 번째만 검사함")
        named = _named_connections(insts[0][1])
        if named is None:
            E("dut_positional_ports", "DUT 포트를 위치 기반으로 연결함 - 이름 기반(.port(sig))만 허용")
        else:
            conns = named
            missing = [p for p in ports if p not in named]
            extra = [p for p in named if p not in ports]
            if missing:
                E("dut_port_missing", f"DUT 포트 연결 빠짐: {missing}")
            if extra:
                E("dut_port_unknown", f"DUT에 없는 포트를 연결함: {extra}")

    # --- 입력이 실제로 구동되는가 (X 입력으로 도는 TB 방지)
    drive_ports = list(summary["inputs_to_drive"]) + [c["port"] for c in summary["clocks"]] \
        + [r["port"] for r in summary["resets"]]
    for p in drive_ports:
        sig = _base_ident(conns.get(p, "")) if conns else None
        if sig and not _assigned(body, sig):
            E("input_undriven", f"입력 '{p}'에 연결된 TB 신호 '{sig}'에 값을 대입하는 곳이 없음")

    # --- 출력이 관찰되는가: 출력에 연결된 신호가 연결부 밖에서 한 번이라도 쓰이는가
    outside = body
    if insts:
        outside = body.replace(insts[0][1], "", 1)
    for p in summary["outputs_to_observe"]:
        sig = _base_ident(conns.get(p, "")) if conns else None
        if sig and not re.search(rf"(?<![\w.]){re.escape(sig)}\b", _after_decl(outside, sig)):
            W("output_unobserved", f"출력 '{p}'(신호 '{sig}')를 비교나 참조하는 곳이 없음")
    if not re.search(r"[!=]==", src):
        W("no_case_equality", "`===`/`!==` 비교가 없음 - X/Z 값이 `==`/`!=`에서 통과될 수 있음")

    # --- 판정 로그 규약 ([TB] PASS / [TB] FAIL), Phase 2 파서와의 계약
    lits = _string_literals(src)
    marks = [s for s in lits if s.lstrip().startswith("[TB]")]
    if not any(re.match(r"\[TB\] PASS\s*$", s) for s in marks):
        E("no_pass_marker", '`$display("[TB] PASS")` 가 없음 - PASS는 이 마커가 있을 때만 인정됨')
    if not any(re.match(r"\[TB\] FAIL", s) for s in marks):
        E("no_fail_marker", '`$display("[TB] FAIL: ...")` 가 없음')
    for s in marks:
        if not re.match(r"\[TB\] (PASS\s*$|FAIL)", s):
            E("bad_tb_marker", f"[TB] 접두 로그는 PASS/FAIL 판정에만 사용 가능: {s[:40]!r}")
    for s in lits:
        if re.match(r"\s*(Error|Fatal)\b\s*:", s):
            W("fake_error_text", f"문자열이 'Error:'로 시작 - 판정은 [TB] 마커로만 하세요: {s[:40]!r}")

    # --- 종료와 금지 태스크
    if not re.search(r"\$finish\b", src):
        E("no_finish", "$finish가 없음 - xsim이 끝나지 않을 수 있음")
    if re.search(r"\$stop\b", src):
        E("uses_stop", "$stop은 xsim batch 실행을 멈출 수 있어 사용 금지")
    if re.search(r"\$(fatal|error)\b", src):
        E("uses_error_task", "$fatal/$error는 시뮬레이터 에러 로그를 만들어 TB 판정과 섞임 - 사용 금지")
    if re.search(r"\$(dumpfile|dumpvars|dumpon|dumpoff)\b", src):
        E("uses_dump", "VCD는 Agent의 Tcl이 생성함 - TB에서 $dumpfile/$dumpvars 사용 금지")
    # 휴리스틱: `initial` 바로 뒤가 지연(#N)이면 워치독으로 본다 (`initial begin #N; ... $finish; end`)
    if not re.search(r"\binitial\s*(?:begin\s*)?#\s*\d+", src):
        W("no_watchdog", "워치독(`initial #N ... $finish`)을 찾지 못함 - 대기 조건이 영영 안 풀리면 멈춤")

    # --- 참고용 로그 규약 (없어도 평가는 되지만 리포트에서 시각과 신호를 못 씀)
    if not any(s.startswith("CHECK_FAIL") for s in lits):
        W("no_check_fail_log", "CHECK_FAIL 로그가 없음 - 실패 시각과 신호가 리포트에 안 나옴")
    if not any(s.startswith("CHECKS total=") for s in lits):
        W("no_checks_summary", "`CHECKS total=... mismatches=...` 요약이 없음")
    if not re.search(r"\$random\b", src):
        W("no_random", "랜덤 자극이 없음 ($random(seed)) - 방향성 시나리오만으로는 경계 조합을 놓칠 수 있음")
    return issues


def _strip_strings(code: str) -> str:
    """문자열 리터럴 안의 단어(예: "int")가 키워드로 잡히지 않게 비운다."""
    return re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', code)


def _after_decl(body: str, sig: str) -> str:
    """신호 선언 줄(`wire [7:0] sig;`)을 제거한 본문. 선언만 있는 신호는 '관찰 안 됨'으로 본다."""
    return re.sub(rf"\b(?:wire|reg)\b[^;]*?\b{re.escape(sig)}\b[^;]*;", " ", body)
