"""Phase 7-2: Debug Agent의 대화 규약(프로토콜)과 프롬프트.

왜 제공자의 function calling이 아니라 텍스트 JSON 규약인가
- 지금 LLM 계층은 `generate(prompt) -> text` 하나다. 이 인터페이스 위에 규약을 얹으면 제공자를 바꿔도
  (Gemini -> 다른 모델) Agent 코드가 그대로고, SystemVerilog/UVM 확장 때도 프롬프트만 바꾸면 된다.
- 요청이 "초기 증거 + 지금까지의 대화 전체"로 결정되므로 기존 디스크 캐시가 그대로 동작한다 (재실행 시 호출 0).
- 단점: 형식 오류가 나올 수 있다. 그래서 파서는 오류 이유를 문장으로 돌려주고, 루프가 그것을 되먹인다.

LLM의 매 응답은 JSON 객체 **하나**:
  {"thought": "...", "action": "tool", "tool": "read_rtl", "args": {...}}
  {"thought": "...", "action": "final", "report": {...}}

공개 API:
    parse_action(text) -> Action                    (형식 오류는 ProtocolError, 메시지를 LLM에 되먹임)
    validate_report(report, files) -> list[str]     (문제 목록, 빈 리스트면 통과)
    build_system_prompt(specs) -> str
    build_initial_message(ev) -> str
    build_prompt(initial, turns, steps_left) -> str
    evidence_from_log(...) -> Evidence
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from core.evaluator import CheckFail, parse_check_fails, parse_checks

MAX_OBS_CHARS = 3000
VERDICTS = ("rtl_bug", "tb_issue", "unknown")
CONFIDENCE = ("high", "medium", "low")


class ProtocolError(Exception):
    """LLM 응답이 규약을 어김. str(e)가 LLM에게 되돌려줄 설명이다."""


@dataclass
class Action:
    kind: str                                 # "tool" | "final"
    thought: str = ""
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    report: dict[str, Any] | None = None
    normalized: bool = False                  # {"action": "<도구이름>", ...} 평탄 호출을 tool 호출로 바꾼 경우


# ---------------------------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------------------------
_FENCE = re.compile(r"```(?:json|JSON)?\s*\n(.*?)```", re.S)


def _json_objects(text: str) -> list[Any]:
    """텍스트에서 최상위 JSON 객체들을 모두 뽑는다 (펜스 안이든 밖이든)."""
    dec = json.JSONDecoder()
    out: list[Any] = []
    i = 0
    while i < len(text):
        j = text.find("{", i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(text, j)
        except json.JSONDecodeError:
            i = j + 1
            continue
        out.append(obj)
        i = end
    return out


def parse_action(text: str, tool_names: set[str] | frozenset[str] | None = None) -> Action:
    """응답에서 action 하나를 뽑는다.

    tool_names를 주면 `{"action": "propose_fix", "file": ..., "find": ...}`처럼 action 자리에 도구 이름을 쓰고
    인자를 최상위에 평탄하게 쓴 호출을 tool 호출로 정규화한다 (v0c 형식 오류 5건이 모두 이 부류). 의도가
    명확하고 모호하지 않을 때만 받아들이며, Action.normalized로 표시해 집계에서 보이게 한다.
    """
    if not text or not text.strip():
        raise ProtocolError("응답이 비어 있다. JSON 객체 하나로 답하라.")
    objs = _json_objects(text)
    objs = [o for o in objs if isinstance(o, dict) and "action" in o]
    if not objs:
        raise ProtocolError('유효한 JSON action을 찾지 못했다. {"thought":..., "action":"tool"|"final", ...} 형식의 '
                            "JSON 객체 하나로 답하라.")
    if len(objs) > 1:
        raise ProtocolError("한 번의 응답에 action이 여러 개 있다. 한 번에 하나의 action만 보내라.")
    o = objs[0]
    kind = o.get("action")
    thought = o.get("thought", "")
    thought = thought if isinstance(thought, str) else str(thought)
    if kind == "tool":
        tool = o.get("tool")
        if not isinstance(tool, str) or not tool:
            raise ProtocolError('action이 "tool"이면 "tool"에 도구 이름(문자열)이 필요하다.')
        args = o.get("args", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ProtocolError('"args"는 JSON 객체여야 한다.')
        return Action("tool", thought, tool=tool, args=args)
    if kind == "final":
        rep = o.get("report")
        if not isinstance(rep, dict):
            raise ProtocolError('action이 "final"이면 "report"에 JSON 객체가 필요하다.')
        return Action("final", thought, report=rep)
    if tool_names and isinstance(kind, str) and kind in tool_names and o.get("tool") in (None, kind):
        args = o.get("args")
        if not isinstance(args, dict):
            args = {k: v for k, v in o.items() if k not in ("action", "thought", "tool", "args")}
        return Action("tool", thought, tool=kind, args=args, normalized=True)
    raise ProtocolError(f'알 수 없는 action: {kind!r}. "tool" 또는 "final"만 허용된다.')


# ---------------------------------------------------------------------------------------------
# 최종 보고서 검증 (구조만. 증거가 실제로 있었는지는 루프가 확인한다)
# ---------------------------------------------------------------------------------------------
def validate_report(report: dict[str, Any], rtl_files: list[str], n_steps_done: int | None = None,
                    valid_steps: set[int] | None = None) -> list[str]:
    """최종 보고서의 문제 목록. 비어 있으면 통과.

    valid_steps: 도구를 실제로 호출한 단계 번호 집합. 주면 근거의 step이 여기에 있어야 한다 (형식 오류로 날린 단계는 근거가 될 수 없음).
    n_steps_done: valid_steps가 없을 때 1..n 범위만 확인한다.
    """
    p: list[str] = []
    v = report.get("verdict")
    if v not in VERDICTS:
        p.append(f"verdict는 {VERDICTS} 중 하나여야 한다 (받은 값: {v!r}).")
    if report.get("confidence") not in CONFIDENCE:
        p.append(f"confidence는 {CONFIDENCE} 중 하나여야 한다.")
    for k in ("summary", "root_cause"):
        if not isinstance(report.get(k), str) or not report[k].strip():
            p.append(f"{k}는 비어 있지 않은 문자열이어야 한다.")
    loc = report.get("location")
    if v == "rtl_bug":
        if not isinstance(loc, dict):
            p.append("verdict가 rtl_bug이면 location({file, line})이 필요하다.")
        else:
            f, ln = loc.get("file"), loc.get("line")
            if f not in rtl_files:
                p.append(f"location.file은 RTL 논리 이름이어야 한다 ({sorted(rtl_files)} 중 하나, 받은 값: {f!r}).")
            if not isinstance(ln, int) or isinstance(ln, bool) or ln < 1:
                p.append("location.line은 1 이상의 정수여야 한다.")
    ev = report.get("evidence")
    if v in ("rtl_bug", "tb_issue"):
        if not isinstance(ev, list) or not ev:
            p.append("evidence(근거)가 최소 1개 필요하다: [{\"step\": 도구를 호출한 단계 번호, \"observation\": \"그 결과에서 본 것\"}].")
        else:
            for i, e in enumerate(ev):
                if (not isinstance(e, dict) or not isinstance(e.get("step"), int) or isinstance(e.get("step"), bool)
                        or not isinstance(e.get("observation"), str) or not e["observation"].strip()):
                    p.append(f"evidence[{i}]는 {{\"step\": 정수, \"observation\": 문자열}} 형식이어야 한다.")
                elif valid_steps is not None and e["step"] not in valid_steps:
                    p.append(f"evidence[{i}].step={e['step']}은 도구를 호출한 단계가 아니다 (도구를 호출한 단계: {sorted(valid_steps)}).")
                elif valid_steps is None and n_steps_done is not None and not (1 <= e["step"] <= n_steps_done):
                    p.append(f"evidence[{i}].step={e['step']}은 실제로 수행한 단계(1..{n_steps_done})가 아니다.")
    ids = report.get("fix_proposal_ids", [])
    if not isinstance(ids, list) or any((not isinstance(x, int) or isinstance(x, bool)) for x in ids):
        p.append("fix_proposal_ids는 정수 리스트여야 한다.")
    return p


# ---------------------------------------------------------------------------------------------
# 초기 증거
# ---------------------------------------------------------------------------------------------
@dataclass
class Evidence:
    top: str
    status: str                               # 보통 "FAIL"
    tb_verdict: str | None
    check_fails: list[CheckFail]              # 앞쪽 N개
    n_check_fails: int
    checks_total: int | None
    checks_mismatches: int | None
    files: dict[str, Any]                     # DebugWorkspace.list_files() 결과
    spec_text: str | None = None
    log_head: str = ""                        # 로그 마지막 몇 줄 (보통 [TB] FAIL/$finish)


def evidence_from_log(top: str, status: str, tb_verdict: str | None, log: str, files: dict[str, Any],
                      spec_text: str | None = None, max_fails: int = 5, tail_lines: int = 6) -> Evidence:
    fails = parse_check_fails(log)
    total, mm = parse_checks(log)
    tail = "\n".join([ln for ln in log.splitlines() if ln.strip()][-tail_lines:])
    return Evidence(top, status, tb_verdict, fails[:max_fails], len(fails), total, mm, files, spec_text, tail)


# ---------------------------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------------------------
def _tool_doc(specs: list[dict[str, Any]]) -> str:
    lines = []
    for s in specs:
        props = s["input_schema"].get("properties", {})
        req = set(s["input_schema"].get("required", []))
        sig = ", ".join(f"{k}{'' if k in req else '?'}: {v.get('type', 'any')}" for k, v in props.items())
        lines.append(f"- {s['name']}({sig})\n    {s['description']}")
    return "\n".join(lines)


def build_system_prompt(specs: list[dict[str, Any]]) -> str:
    return f"""You are a Verilog RTL debugging agent. A self-checking testbench FAILED on a design under test (DUT).
Find the root cause using the tools, then report. You never modify files: you only read evidence and propose fixes.

## Method (follow it)
1. Read the failure summary. Form a hypothesis about WHICH signal is wrong and WHEN it first diverges.
2. Collect evidence with tools before concluding. Prefer the FIRST failing check: later failures are usually consequences.
3. Decide whether the DUT or the testbench is wrong:
   - rtl_bug: the RTL violates the specification. Cite the RTL line.
   - tb_issue: the testbench's expected value or stimulus is wrong (check its reference model with read_tb).
   - unknown: the evidence is insufficient. Say what is missing. Do NOT guess.
4. Never conclude from a value you have not seen. Signal values that are x or whose status is not ok need cross-checking.
5. The line you report must be the line that CAUSES the wrong behavior, not the line where the symptom is first visible.
6. propose_fix only accepts RTL files. If you believe the testbench is wrong, report tb_issue instead of changing it.

## Reply format
Every reply is exactly ONE JSON object, nothing else of substance outside it.

Call a tool:
{{"thought": "why this call", "action": "tool", "tool": "<name>", "args": {{...}}}}

Finish (only when you have evidence):
{{"thought": "...", "action": "final", "report": {{
  "verdict": "rtl_bug" | "tb_issue" | "unknown",
  "location": {{"file": "rtl/<name>.v", "line": <int>}},
  "summary": "one sentence",
  "root_cause": "what is wrong and why it produces the observed failure",
  "evidence": [{{"step": <step number of the tool call>, "observation": "what that result showed"}}],
  "fix_proposal_ids": [<ids returned by propose_fix>],
  "confidence": "high" | "medium" | "low"
}}}}
"location" is required for rtl_bug. "evidence" is required for rtl_bug and tb_issue, and each "step" must be a step in which you actually called a tool.

## Tools
{_tool_doc(specs)}

File names are logical names such as rtl/fifo_ctrl.v. Use exactly those names. Tool results are JSON.
You have a limited number of steps; the remaining count is shown each turn. If you are running out, finish with your best evidence-based report (verdict "unknown" if needed)."""


def _fmt_fail(f: CheckFail) -> str:
    t = f"{f.t_ps} ps" if f.t_ps is not None else "time unknown"
    return f"  - t={t}  sig={f.signal}  expected={f.expected}  got={f.got}"


def build_initial_message(ev: Evidence) -> str:
    parts = [f"# Failure report\nDUT top: {ev.top}\nSimulation status: {ev.status}"
             f"{f'  (testbench verdict: {ev.tb_verdict})' if ev.tb_verdict else ''}"]
    if ev.checks_total is not None:
        parts.append(f"Checks: total={ev.checks_total} mismatches={ev.checks_mismatches}")
    if ev.check_fails:
        more = "" if ev.n_check_fails <= len(ev.check_fails) else f" (showing first {len(ev.check_fails)} of {ev.n_check_fails})"
        parts.append("First failing checks" + more + ":\n" + "\n".join(_fmt_fail(f) for f in ev.check_fails))
    else:
        parts.append("No CHECK_FAIL lines were parsed from the log. Inspect the log with get_log_snippet.")
    if ev.log_head:
        parts.append("Log tail:\n" + ev.log_head)
    fl = ev.files
    parts.append("Files:\n" + "\n".join(
        [f"  {x['file']} ({x['lines']} lines)" for x in fl["rtl"]]
        + [f"  {x['file']} ({x['lines']} lines, testbench, read-only)" for x in fl["tb"]])
        + f"\nVCD available: {'yes' if fl['vcd'] else 'no'}")
    if ev.spec_text:
        parts.append("Specification:\n" + ev.spec_text.strip())
    return "\n\n".join(parts)


def truncate_obs(text: str, limit: int = MAX_OBS_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n...[관측 잘림: 원래 {len(text)}자]"


@dataclass
class Turn:
    step: int                                 # 1부터. 도구를 호출한 단계 번호 (evidence가 이 번호를 인용)
    assistant: str                            # LLM이 보낸 원문 (정규화한 JSON 문자열)
    observation: str                          # 도구 결과(JSON 문자열) 또는 형식 오류 안내


def render_turn(t: Turn) -> str:
    return f"## Step {t.step}\nYOUR ACTION:\n{t.assistant}\nRESULT:\n{truncate_obs(t.observation)}"


def build_prompt(initial: str, turns: list[Turn], steps_left: int) -> str:
    body = [initial]
    body += [render_turn(t) for t in turns]
    body.append(f"[{steps_left} step(s) left. Reply with exactly one JSON object.]")
    if steps_left <= 1:
        body.append('This is your LAST step. Do not call another tool: reply now with action "final". '
                    'If the evidence is insufficient, use verdict "unknown" and say what is missing.')
    return "\n\n".join(body)
