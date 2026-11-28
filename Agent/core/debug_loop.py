"""Phase 7-3: Debug Agent 루프.

  초기 증거 -> [LLM이 JSON action 하나] -> 도구 실행 -> 관측을 대화에 추가 -> ... -> final 보고서

"단계"는 조사 행동(도구 호출, 최종 보고)이다. 형식 오류와 거부된 보고서는 단계로 세지 않는다 (spi0에서 230단계 중 19단계를
먹어 조사 단계가 부족했다). 대신 이런 턴은 케이스당 `max_free_turns`번까지만 허용해 호출량의 상한을 유지한다.

종료 상태 (`DebugRun.status`)
  final          보고서가 검증을 통과했다
  max_steps      단계를 모두 썼는데 보고서가 없다 (정직하게 "못 찾음"으로 기록한다. 억지 보고서를 만들지 않는다)
  format_errors  JSON 형식 오류가 연속으로 한도를 넘었다
  quota          일일 한도 소진
  budget         이번 실행의 호출 상한 초과
  llm_error      그 밖의 LLM 오류 (결제, 서버 오류 재시도 소진 등)

되먹임 규칙
- 형식 오류: 이유를 담은 안내를 관측으로 돌려준다. 연속 `max_format_errors`회면 중단.
- 보고서 거부: 구조 검증 + 의미 검증(없는 줄 번호, 없는 수정안 id, 도구를 호출하지 않은 단계 인용)에 걸리면
  이유를 되먹이고 계속한다.
- 같은 도구를 같은 인자로 다시 부르면 이전 단계를 알려 준다 (같은 확인을 반복하는 루프 방지).

공개 API:
    debug_loop(ws, evidence, client, max_steps=10, ...) -> DebugRun
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from core.debug_protocol import (Evidence, ProtocolError, Turn, build_initial_message, build_prompt,
                                 build_system_prompt, parse_action, validate_report)
from core.debug_tools import DebugWorkspace, dispatch_debug, tool_specs
from llm.base import BudgetExceeded, DailyQuotaExceeded, LLMError, LLMRequest

FORMAT_ERROR_KEEP = 4000          # F4c: 형식 오류 응답 원문 저장 길이 (500자에서는 원인을 볼 수 없던 사례가 있었다)
TIMING_EVIDENCE_TOOLS = frozenset({"read_vcd_signal", "sample_signals", "rerun_sim"})
_TIMING_CLAIM = re.compile(
    r"\b(?:\d+|one|two|single)\s+(?:spi_clk\s+|clock\s+|ck\s+|cycle\s+)?cycles?\b"
    r"|\btoo (?:early|late|short|long)\b|\b(?:only|just) (?:for )?(?:one|1|a single)\b"
    r"|\bimmediately (?:transitions?|goes|returns|moves)\b"
    r"|\b(?:held|asserted|stays?|lasts?|remains?|kept) (?:high|low|asserted)? ?for\b", re.I)


def timing_claim(report: dict[str, Any]) -> str | None:
    """F3b: 보고서가 "N주기 유지", "너무 일찍/늦게" 같은 타이밍 주장을 하면 그 문구를 돌려준다."""
    if report.get("verdict") != "rtl_bug":
        return None
    m = _TIMING_CLAIM.search(f"{report.get('summary') or ''} {report.get('root_cause') or ''}")
    return m.group(0) if m else None


STATUSES = ("final", "max_steps", "format_errors", "quota", "budget", "llm_error")


@dataclass
class StepLog:
    step: int
    kind: str                         # "tool" | "final" | "format_error" | "report_rejected"
    tool: str | None = None
    args: dict[str, Any] | None = None
    note: str = ""                    # 형식 오류/거부 이유 등
    cached: bool = False
    finish_reason: str | None = None  # LLM이 멈춘 이유 (STOP이 아니면 잘렸을 수 있다. 예: MAX_TOKENS)
    retries: int = 0                  # 이 단계에서 빈 응답을 받아 같은 요청을 다시 보낸 횟수
    retry_reasons: list[str | None] = field(default_factory=list)   # 버려진 빈 응답들의 finish_reason


@dataclass
class DebugRun:
    status: str
    report: dict[str, Any] | None = None
    steps: list[StepLog] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    llm_calls: int = 0                # 캐시에서 온 응답은 제외 (실제 호출 한도를 쓴 횟수)
    cached_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    format_errors: int = 0
    rejected_reports: int = 0
    normalized_calls: int = 0         # 평탄한 도구 호출을 정규화해 받아들인 횟수 (형식 오류였을 호출)
    empty_retries: int = 0            # 빈 응답 때문에 다시 보낸 요청 수 (단계와 형식 오류로 세지 않음. llm_calls에는 포함)
    error: str | None = None
    proposals: list[dict[str, Any]] = field(default_factory=list)
    initial_message: str = ""        # Agent이 처음 받은 증거 메시지 (사후 분석에서 Agent가 무엇을 알았는지 확인)
    prompt_sha: str = ""             # 시스템 프롬프트(규약 + 도구 명세)의 해시. 어떤 프롬프트로 얻은 결과인지 구분
    stripped_fix_ids: list[Any] = field(default_factory=list)
    timing_gate_rejections: int = 0   # F3b: 근거 없는 타이밍 주장으로 거부한 횟수 (0 또는 1)   # F5: rerun_sim PASS가 아니라 보고서에서 뺀 수정안 id

    @property
    def n_steps(self) -> int:
        return len(self.steps)

    @property
    def n_tool_calls(self) -> int:
        return sum(1 for s in self.steps if s.kind == "tool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "report": self.report, "error": self.error,
            "n_steps": self.n_steps, "n_tool_calls": self.n_tool_calls,
            "llm_calls": self.llm_calls, "cached_calls": self.cached_calls,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "format_errors": self.format_errors, "rejected_reports": self.rejected_reports,
            "empty_retries": self.empty_retries, "normalized_calls": self.normalized_calls,
            "steps": [vars(s) for s in self.steps],
            "turns": [{"step": t.step, "assistant": t.assistant, "observation": t.observation} for t in self.turns],
            "proposals": self.proposals,
            "prompt_sha": self.prompt_sha, "initial_message": self.initial_message,
            "stripped_fix_ids": self.stripped_fix_ids, "timing_gate_rejections": self.timing_gate_rejections,
        }


def _compact(action_dict: dict[str, Any]) -> str:
    """대화에 다시 넣을 LLM 행동 (원문의 잡담을 빼고 정규화해서 프롬프트를 짧고 결정적으로 유지한다)."""
    return json.dumps(action_dict, ensure_ascii=False, sort_keys=True)


def semantic_problems(report: dict[str, Any], ws: DebugWorkspace, tool_steps: set[int]) -> list[str]:
    """구조 검증을 통과한 보고서의 의미 검증: 존재하지 않는 줄, 수정안 id."""
    out: list[str] = []
    loc = report.get("location")
    if report.get("verdict") == "rtl_bug" and isinstance(loc, dict) and loc.get("file") in ws.rtl:
        n = ws.list_files()["rtl"]
        total = next(x["lines"] for x in n if x["file"] == loc["file"])
        if isinstance(loc.get("line"), int) and loc["line"] > total:
            out.append(f"location.line={loc['line']}이 {loc['file']}의 길이({total}줄)를 넘는다.")
    have = {p.id for p in ws.proposals}
    for pid in report.get("fix_proposal_ids", []) or []:
        if isinstance(pid, int) and pid not in have:
            out.append(f"fix_proposal_ids의 {pid}은 propose_fix가 돌려준 id가 아니다 (있는 id: {sorted(have)}).")
    return out


def strip_unverified_fixes(report: dict[str, Any], ws: DebugWorkspace) -> tuple[dict[str, Any], list[Any]]:
    """F5: fix_proposal_ids에서 rerun_sim이 PASS하지 않은(또는 돌리지 않은) id를 뺀다.

    프롬프트 규칙 7("PASS한 제안만 올려라")을 LLM이 어기는 경우가 spi1에서 4/30이었다. 보고서를 거부하면 턴을 더 쓰므로
    위치 판단은 살리고 검증되지 않은 수정안만 뺀다. rerun_sim 도구가 없는 모드(ws.sim None)에서는 확인할 수단이 없어 그대로 둔다.
    """
    ids = report.get("fix_proposal_ids") or []
    if ws.sim is None or not ids:
        return report, []
    passed = {pid for pid, res in ws.sim_results.items() if res.get("status") == "PASS"}

    def ok(i: Any) -> bool:
        try:
            return int(i) in passed
        except (TypeError, ValueError):
            return False

    kept = [i for i in ids if ok(i)]
    return {**report, "fix_proposal_ids": kept}, [i for i in ids if not ok(i)]


def debug_loop(ws: DebugWorkspace, evidence: Evidence, client, max_steps: int = 10,
               max_format_errors: int = 3, max_free_turns: int = 3, model: str | None = None, temperature: float = 0.0,
               max_output_tokens: int | None = 1500, empty_retries: int = 2,
               on_step: Callable[[StepLog], None] | None = None) -> DebugRun:
    system = build_system_prompt(tool_specs(ws))
    initial = build_initial_message(evidence)
    run = DebugRun(status="max_steps", initial_message=initial,
                   prompt_sha=hashlib.sha256(system.encode("utf-8")).hexdigest()[:12])
    tool_steps: set[int] = set()
    tools_used: set[str] = set()
    timing_gate_used = False                  # F3b: 타이밍 주장 거부는 케이스당 1회
    seen_calls: dict[str, int] = {}
    consecutive_fmt = 0
    rtl_names = sorted(ws.rtl)
    tool_names = frozenset(sp["name"] for sp in tool_specs(ws))

    def record(log: StepLog, assistant: str, observation: str) -> None:
        run.steps.append(log)
        run.turns.append(Turn(log.step, assistant, observation))
        if on_step:
            on_step(log)

    used = 0                                  # 쓴 조사 단계 (도구 호출)
    step = 0                                  # 턴 번호. evidence가 인용하는 번호라 형식 오류 턴도 번호를 받는다
    while used < max_steps and step < max_steps + max_free_turns:
        step += 1
        prompt = build_prompt(initial, run.turns, max_steps - used)
        retries, retry_reasons = 0, []
        resp = None
        while True:
            try:
                resp = client.generate(LLMRequest(prompt=prompt, system=system, model=model,
                                                  temperature=temperature, max_output_tokens=max_output_tokens))
            except DailyQuotaExceeded as e:
                run.status, run.error = "quota", str(e)
                resp = None
                break
            except BudgetExceeded as e:
                run.status, run.error = "budget", str(e)
                resp = None
                break
            except LLMError as e:
                run.status, run.error = "llm_error", f"{type(e).__name__}: {e}"
                resp = None
                break

            run.input_tokens += resp.input_tokens
            run.output_tokens += resp.output_tokens
            if resp.cached:
                run.cached_calls += 1
            else:
                run.llm_calls += 1
            # 빈 응답은 모델의 추론 결과가 아니라 전송 단계의 실패(예: MALFORMED_FUNCTION_CALL)일 때가 많다.
            # 같은 요청을 다시 보낸다. 이 재시도는 단계와 형식 오류로 세지 않는다 (호출 한도에는 포함).
            if resp.text.strip() or retries >= empty_retries:
                break
            retries += 1
            retry_reasons.append(resp.finish_reason)
            run.empty_retries += 1
        if resp is None:
            break

        try:
            act = parse_action(resp.text, tool_names)
        except ProtocolError as e:
            run.format_errors += 1
            consecutive_fmt += 1
            msg = f"FORMAT ERROR: {e}"
            fr = resp.finish_reason
            extra = f" [finish_reason={fr}]" if fr not in (None, "STOP") else ""
            record(StepLog(step, "format_error", note=str(e) + extra, cached=resp.cached, finish_reason=fr,
                           retries=retries, retry_reasons=retry_reasons),
                   resp.text.strip()[:FORMAT_ERROR_KEEP], json.dumps({"error": msg}, ensure_ascii=False))
            if consecutive_fmt >= max_format_errors:
                run.status, run.error = "format_errors", f"형식 오류 {consecutive_fmt}회 연속"
                break
            continue
        consecutive_fmt = 0

        if act.kind == "tool":
            key = json.dumps([act.tool, act.args], sort_keys=True, ensure_ascii=False)
            result = dispatch_debug(ws, act.tool, act.args)
            if key in seen_calls:
                result = {"note": f"step {seen_calls[key]}에서 같은 도구를 같은 인자로 이미 호출했다. "
                                  "새로운 증거를 찾거나 결론을 내려라.", **result}
            else:
                seen_calls[key] = step
            tool_steps.add(step)
            tools_used.add(act.tool)
            used += 1
            if act.normalized:
                run.normalized_calls += 1
            record(StepLog(step, "tool", act.tool, act.args,
                           note="평탄한 호출을 tool 호출로 정규화" if act.normalized else "", cached=resp.cached, finish_reason=resp.finish_reason,
                           retries=retries, retry_reasons=retry_reasons),
                   _compact({"thought": act.thought, "action": "tool", "tool": act.tool, "args": act.args}),
                   json.dumps(result, ensure_ascii=False))
            continue

        # final
        problems = validate_report(act.report, rtl_names, valid_steps=tool_steps)
        if not problems:
            problems = semantic_problems(act.report, ws, tool_steps)
        claim = timing_claim(act.report) if not problems else None
        if (claim and not timing_gate_used and not (tools_used & TIMING_EVIDENCE_TOOLS)
                and (ws.vcd is not None or ws.sim is not None)):
            timing_gate_used = True
            run.timing_gate_rejections += 1
            problems = [f'타이밍 주장("{claim}")을 파형이나 재시뮬레이션으로 확인하지 않았다. 그 신호에 값을 넣는 모든 '
                        "상태를 search_rtl로 찾고, read_vcd_signal/sample_signals 또는 rerun_sim으로 실제 타이밍을 "
                        "확인한 뒤 보고하라 (확인 결과 주장이 맞으면 같은 결론을 다시 보내도 된다)."]
        if problems:
            run.rejected_reports += 1
            note = "; ".join(problems)
            record(StepLog(step, "report_rejected", note=note, cached=resp.cached, finish_reason=resp.finish_reason,
                           retries=retries, retry_reasons=retry_reasons),
                   _compact({"thought": act.thought, "action": "final", "report": act.report}),
                   json.dumps({"error": "REPORT REJECTED. Fix these and send a corrected final report "
                                        "(or call more tools if you need evidence): " + note},
                              ensure_ascii=False))
            continue
        record(StepLog(step, "final", cached=resp.cached, finish_reason=resp.finish_reason,
                       retries=retries, retry_reasons=retry_reasons),
               _compact({"thought": act.thought, "action": "final", "report": act.report}), "{}")
        run.report, run.stripped_fix_ids = strip_unverified_fixes(act.report, ws)
        run.status = "final"
        break

    run.proposals = [p.to_dict() for p in ws.proposals]
    return run
