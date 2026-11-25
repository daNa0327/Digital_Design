"""Phase 7-4: Debug Agent 평가.

질문: "TB가 실패시킨 RTL 변형에서 Agent가 원인 위치를 맞히는가?"

흐름 (변형 하나당)
  골든에 버그 패치 적용 -> 사람 TB로 실행 -> FAIL이면 Agent 실행 -> 보고서를 정답(파일, 줄, 유형)과 대조
- 사람 TB를 쓰는 이유: 골든 PASS가 검증된 TB라서 변형의 FAIL은 정의상 RTL 버그다. TB 품질과 Agent 품질을 섞지 않는다.
- 동등 변형(관측 불가능한 변형)은 평가하지 않는다. 실행했는데 FAIL이 아니면 Agent를 부르지 않고 `not_failed`로 기록한다.
- Agent는 변형 ID, 카탈로그 설명, 변형 diff, 실제 경로를 볼 수 없다 (`debug_tools.workspace_from_files`가 경로를 논리 이름으로 바꿈).

결과 분류 (`Score.category`, 위에서부터 처음 해당하는 것)
  no_report        Agent가 보고서 없이 끝남 (max_steps, 형식 오류, LLM 오류 등)
  not_rtl_bug      verdict가 tb_issue 또는 unknown (사람 TB의 FAIL이므로 정답은 rtl_bug)
  wrong_file       다른 RTL 파일을 지목
  wrong_line       같은 파일이지만 정답 줄에서 `near`줄보다 멀다
  near             같은 파일, 정답 줄에서 1..near줄 떨어짐
  exact            정답 줄을 정확히 지목

정답 줄은 "패치가 적용된 줄"이다. 원인과 증상이 다른 줄에 있는 버그는 정답 줄이 원인 쪽이므로 증상 줄을 지목하면 near/wrong_line이 된다.

이어하기: 케이스마다 `cases/<id>.json`을 저장한다. 일일 호출 한도로 중간에 멈춰도 다음 날 `resume`으로 끝난 케이스는 건너뛴다
(quota/budget/llm_error로 끝난 케이스는 다시 실행).

공개 API:
    score_case(report, truth, near=2) -> Score
    run_debug_eval(...) -> DebugEvalReport
    summarize_cases(cases) -> dict
    render_markdown(report, label) -> str
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.bugs import Bug, apply_bug
from core.debug_loop import DebugRun, StepLog, debug_loop
from core.debug_protocol import evidence_from_log
from core.debug_tools import workspace_from_files
from core.evaluator import Judged, Runner
from core.fix_verify import FIX_CATEGORIES, check_fix, make_sim_fn

CATEGORIES = ("exact", "near", "wrong_line", "wrong_file", "not_rtl_bug", "no_report")
DONE_STATUSES = ("final", "max_steps", "format_errors")     # 이어하기에서 다시 실행하지 않는 종료 상태
NEAR = 2
# "실패 증거를 더 모으는" 도구: 로그, TB, 파형. read_rtl/search_rtl/list_signals는 코드나 목록을 볼 뿐이라 제외한다.
EVIDENCE_TOOLS = ("get_log_snippet", "read_tb", "read_vcd_signal", "sample_signals")


@dataclass(frozen=True)
class Truth:
    bug_id: str
    type: str
    file: str            # 논리 이름 (예: rtl/fifo_ctrl.v)
    line: int


@dataclass
class Score:
    category: str
    verdict: str | None
    file_ok: bool
    line_delta: int | None            # |지목한 줄 - 정답 줄|, 파일이 다르거나 보고서가 없으면 None
    confidence: str | None

    @property
    def located(self) -> bool:        # 정답 줄 주변(near 이내)을 맞힘
        return self.category in ("exact", "near")


def score_case(report: dict[str, Any] | None, truth: Truth, near: int = NEAR) -> Score:
    if report is None:
        return Score("no_report", None, False, None, None)
    verdict, conf = report.get("verdict"), report.get("confidence")
    if verdict != "rtl_bug":
        return Score("not_rtl_bug", verdict, False, None, conf)
    loc = report.get("location") or {}
    file_ok = loc.get("file") == truth.file
    if not file_ok:
        return Score("wrong_file", verdict, False, None, conf)
    delta = abs(int(loc["line"]) - truth.line)
    cat = "exact" if delta == 0 else "near" if delta <= near else "wrong_line"
    return Score(cat, verdict, True, delta, conf)


@dataclass
class Case:
    bug_id: str
    type: str
    outcome: str                       # "evaluated" | "not_failed" | "equivalent_skipped" | "not_run"
    sim_status: str | None = None
    truth: dict[str, Any] | None = None
    run: dict[str, Any] | None = None  # DebugRun.to_dict()
    score: dict[str, Any] | None = None
    resumed: bool = False              # 이전 실행에서 가져온 케이스
    fix: dict[str, Any] | None = None  # 7-5: 수정안 검증 결과 (fix_verify.FixResult.to_dict() + agent_sims)

    def to_dict(self) -> dict[str, Any]:
        return {"bug_id": self.bug_id, "type": self.type, "outcome": self.outcome, "sim_status": self.sim_status,
                "truth": self.truth, "run": self.run, "score": self.score, "fix": self.fix}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Case":
        return cls(d["bug_id"], d["type"], d["outcome"], d.get("sim_status"), d.get("truth"), d.get("run"),
                   d.get("score"), resumed=True, fix=d.get("fix"))


@dataclass
class DebugEvalReport:
    dut: str
    cases: list[Case] = field(default_factory=list)
    aborted_reason: str | None = None      # quota/budget 등으로 중간에 멈춘 이유
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> dict[str, Any]:
        return summarize_cases(self.cases)

    def to_dict(self) -> dict[str, Any]:
        return {"dut": self.dut, "aborted_reason": self.aborted_reason, "meta": self.meta,
                "summary": self.summary, "cases": [c.to_dict() for c in self.cases]}


# ---------------------------------------------------------------------------------------------
# 집계
# ---------------------------------------------------------------------------------------------
def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def summarize_cases(cases: list[Case]) -> dict[str, Any]:
    """평가된 케이스의 지표. 분모는 "Agent가 실제로 실행된 케이스"다 (not_failed, 동등, 미실행 제외)."""
    ev = [c for c in cases if c.outcome == "evaluated"]
    n = len(ev)
    cat = {k: 0 for k in CATEGORIES}
    status: dict[str, int] = {}
    for c in ev:
        cat[c.score["category"]] += 1
        status[c.run["status"]] = status.get(c.run["status"], 0) + 1

    def rate(k: int) -> float | None:
        return k / n if n else None

    finals = [c for c in ev if c.run["status"] == "final"]
    steps = [c.run["n_steps"] for c in finals]
    total_steps = sum(c.run["n_steps"] for c in ev)
    fmt = sum(c.run["format_errors"] for c in ev)
    # STOP이 아닌 이유로 끝난 응답 (MAX_TOKENS 등): 빈 응답이나 잘린 JSON의 원인 후보
    non_stop = sum(1 for c in ev for s in c.run.get("steps", []) if s.get("finish_reason") not in (None, "STOP"))
    # 빈 응답 재시도: 보낸 횟수와, 재시도로 정상 응답을 받아 단계를 이어간 횟수
    normalized = sum(c.run.get("normalized_calls", 0) for c in ev if c.run)
    retries_sent = sum(c.run.get("empty_retries", 0) for c in ev)
    retries_recovered = sum(1 for c in ev for s in c.run.get("steps", [])
                            if s.get("retries", 0) > 0 and s.get("kind") != "format_error")
    by_type: dict[str, dict[str, int]] = {}
    for c in ev:
        t = by_type.setdefault(c.type, {"n": 0, "located": 0, "exact": 0})
        t["n"] += 1
        t["exact"] += c.score["category"] == "exact"
        t["located"] += c.score["category"] in ("exact", "near")
    # 확신도 보정: 확신도 별로 맞은 비율. "high인데 틀림"이 위험 신호다.
    calib: dict[str, dict[str, int]] = {}
    for c in finals:
        k = c.score["confidence"] or "none"
        b = calib.setdefault(k, {"n": 0, "located": 0})
        b["n"] += 1
        b["located"] += c.score["category"] in ("exact", "near")
    usage: dict[str, int] = {}
    for c in ev:
        for st in c.run.get("steps", []):
            if st.get("kind") == "tool" and st.get("tool"):
                usage[st["tool"]] = usage.get(st["tool"], 0) + 1
    evidence_cases = [c.bug_id for c in ev
                      if any(st.get("tool") in EVIDENCE_TOOLS for st in c.run.get("steps", []) if st.get("kind") == "tool")]
    fixed = [c for c in ev if c.fix]
    fix_cat = {k: 0 for k in FIX_CATEGORIES}
    for c in fixed:
        fix_cat[c.fix["category"]] += 1
    # Agent가 rerun_sim으로 직접 확인한 횟수와, 그 결과가 사후 검증과 일치했는지
    agent_sims = sum(len(c.fix.get("agent_sims") or {}) for c in fixed)
    return {
        "tool_usage": dict(sorted(usage.items(), key=lambda kv: (-kv[1], kv[0]))),
        "evidence_tool_cases": evidence_cases,
        "n_fix_verified": len(fixed), "fix_categories": fix_cat, "agent_sim_runs": agent_sims,
        "fix_pass_rate": (fix_cat["fixed_golden"] + fix_cat["fixed_pass"]) / len(fixed) if fixed else None,
        "fix_golden_rate": fix_cat["fixed_golden"] / len(fixed) if fixed else None,
        "located_but_not_fixed": [c.bug_id for c in fixed if c.score["category"] in ("exact", "near")
                                  and c.fix["category"] not in ("fixed_golden", "fixed_pass")],
        "n_cases": len(cases), "n_evaluated": n,
        "n_not_failed": sum(c.outcome == "not_failed" for c in cases),
        "n_not_run": sum(c.outcome == "not_run" for c in cases),
        "n_equivalent_skipped": sum(c.outcome == "equivalent_skipped" for c in cases),
        "categories": cat, "run_status": status,
        "report_rate": rate(len(finals)),
        "rtl_bug_rate": rate(n - cat["not_rtl_bug"] - cat["no_report"]),
        "file_accuracy": rate(cat["exact"] + cat["near"] + cat["wrong_line"]),
        "exact_rate": rate(cat["exact"]),
        "located_rate": rate(cat["exact"] + cat["near"]),
        "mean_steps_final": _mean(steps),
        "mean_steps_all": total_steps / n if n else None,
        "mean_tool_calls": _mean([c.run["n_tool_calls"] for c in ev]),
        "llm_calls": sum(c.run["llm_calls"] for c in ev),
        "cached_calls": sum(c.run["cached_calls"] for c in ev),
        "format_error_rate": fmt / total_steps if total_steps else None,
        "non_stop_steps": non_stop,
        "normalized_calls": normalized, "empty_retries": retries_sent, "empty_retries_recovered": retries_recovered,
        "rejected_reports": sum(c.run["rejected_reports"] for c in ev),
        "input_tokens": sum(c.run["input_tokens"] for c in ev),
        "output_tokens": sum(c.run["output_tokens"] for c in ev),
        "by_type": by_type, "confidence": calib,
        "high_conf_wrong": [c.bug_id for c in finals if c.score["confidence"] == "high"
                            and c.score["category"] not in ("exact", "near")],
    }


# ---------------------------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------------------------
def default_vcd_loader(path: str | None):
    """VCD 경로에서 VcdTools를 만든다. 없거나 읽지 못하면 None (VCD 없이 Agent를 돌린다)."""
    if not path or not Path(path).is_file():
        return None
    try:
        from core.vcd_reader import VcdReader
        from core.vcd_tools import VcdTools
        return VcdTools(VcdReader.from_file(path))
    except Exception:
        return None


def _save_case(cases_dir: Path, case: Case) -> None:
    cases_dir.mkdir(parents=True, exist_ok=True)
    (cases_dir / f"{case.bug_id}.json").write_text(
        json.dumps(case.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _load_case(cases_dir: Path, bug_id: str) -> Case | None:
    p = cases_dir / f"{bug_id}.json"
    if not p.is_file():
        return None
    try:
        return Case.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError):
        return None


def run_debug_eval(bugs: list[Bug], golden_rtl_dir: str | Path, tb_path: str | Path, tb_top: str,
                   dut_top: str, runner: Runner, client, work_root: str | Path, dut: str = "dut",
                   spec_text: str | None = None, max_steps: int = 8, near: int = NEAR, resume: bool = False,
                   max_output_tokens: int | None = 4096, empty_retries: int = 1,
                   sim_tool: bool = False, verify_fixes: bool = False,
                   vcd_loader: Callable[[str | None], Any] = default_vcd_loader,
                   progress: Callable[[str], None] | None = None) -> DebugEvalReport:
    say = progress or (lambda s: None)
    golden_dir, root = Path(golden_rtl_dir), Path(work_root)
    cases_dir = root / "cases"
    report = DebugEvalReport(dut, meta={"tb": Path(tb_path).as_posix(), "tb_top": tb_top, "max_steps": max_steps,
                                        "near": near})
    aborted = False
    for i, bug in enumerate(bugs, 1):
        if bug.equivalent:
            report.cases.append(Case(bug.id, bug.type, "equivalent_skipped"))
            continue
        if aborted:
            report.cases.append(Case(bug.id, bug.type, "not_run"))
            continue
        if resume:
            old = _load_case(cases_dir, bug.id)
            if old is not None and (old.outcome == "not_failed" or
                                    (old.run and old.run["status"] in DONE_STATUSES)):
                say(f"[{i}/{len(bugs)}] {bug.id}: 이전 결과 사용")
                report.cases.append(old)
                continue

        say(f"[{i}/{len(bugs)}] {bug.id}: 변형 실행")
        if (root / bug.id).exists():          # 이전에 한도로 끝난 케이스의 작업 폴더 (apply_bug와 xsim은 기존 폴더를 거부함)
            shutil.rmtree(root / bug.id)
        applied = apply_bug(bug, golden_dir, root / bug.id / "rtl")
        files = sorted(str(p) for p in applied.rtl_dir.glob("*.v")) + [str(tb_path)]
        j: Judged = runner(files, tb_top, str(root / bug.id / "run"))
        truth = Truth(bug.id, bug.type, f"rtl/{bug.file}", applied.line)
        if j.status != "FAIL":
            case = Case(bug.id, bug.type, "not_failed", j.status, truth=vars(truth))
            _save_case(cases_dir, case)
            report.cases.append(case)
            say(f"  사람 TB가 FAIL시키지 않음 ({j.status}): Agent 평가 대상 아님")
            continue

        ws = workspace_from_files(sorted(applied.rtl_dir.glob("*.v")), [tb_path], j.xsim_stdout,
                                  vcd_tools=vcd_loader(j.vcd_path))
        ev = evidence_from_log(dut_top, j.status, j.tb_verdict, ws.log, ws.list_files(), spec_text=spec_text)
        if sim_tool:        # Agent가 수정안을 원본 TB로 재시뮬레이션해 볼 수 있다 (rerun_sim 도구)
            ws.sim = make_sim_fn(runner, [tb_path], tb_top, root / bug.id / "agent_sim")
        say("  Agent 실행")
        run: DebugRun = debug_loop(ws, ev, client, max_steps=max_steps, max_output_tokens=max_output_tokens,
                                   empty_retries=empty_retries,
                                   on_step=lambda s: say(f"    step {s.step}: {s.kind}"
                                                         f"{' ' + s.tool if s.tool else ''}"))
        sc = score_case(run.report, truth, near)
        case = Case(bug.id, bug.type, "evaluated", j.status, truth=vars(truth), run=run.to_dict(),
                    score={"category": sc.category, "verdict": sc.verdict, "file_ok": sc.file_ok,
                           "line_delta": sc.line_delta, "confidence": sc.confidence})
        if verify_fixes and run.status not in ("quota", "budget", "llm_error"):
            say("  수정안 검증")
            golden_rtl = {f"rtl/{p.name}": p.read_text(encoding="utf-8", errors="replace")
                          for p in sorted(golden_dir.glob("*.v"))}
            fx = check_fix(run.report, run.proposals, ws.rtl, golden_rtl,
                           make_sim_fn(runner, [tb_path], tb_top, root / bug.id / "verify")).to_dict()
            fx["agent_sims"] = {str(i): r.get("status") for i, r in ws.sim_results.items()}
            case.fix = fx
            say(f"  수정안: {fx['category']}")
        if run.status in ("quota", "budget", "llm_error"):
            # 한도 문제로 끝난 케이스는 저장하되 이어하기에서 다시 실행한다. 이후 변형은 실행하지 않는다.
            aborted = True
            report.aborted_reason = f"{bug.id}: {run.status} ({run.error})"
            say(f"  중단: {report.aborted_reason}")
        _save_case(cases_dir, case)
        report.cases.append(case)
        say(f"  -> {run.status}, {sc.category}, 단계 {run.n_steps}, 호출 {run.llm_calls}")
    # 어떤 프롬프트로 얻은 결과인지 기록한다 (이어하기 중 프롬프트가 바뀌면 서로 다른 값이 섞이므로 경고에 쓴다)
    report.meta["prompt_shas"] = sorted({c.run.get("prompt_sha") for c in report.cases
                                        if c.run and c.run.get("prompt_sha")})
    return report


# ---------------------------------------------------------------------------------------------
# 리포트
# ---------------------------------------------------------------------------------------------
def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _num(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}"


def render_markdown(report: DebugEvalReport, label: str = "") -> str:
    s = report.summary
    L = [f"# Debug Agent 평가: {report.dut}" + (f" ({label})" if label else ""), ""]
    m = report.meta
    L.append(f"입력 TB: `{m.get('tb')}` (사람이 쓴 self-checking TB, 골든 PASS 검증됨). 최대 단계 {m.get('max_steps')}, "
             f"줄 허용 오차 {m.get('near')}줄.")
    shas = m.get("prompt_shas") or []
    if shas:
        L.append(f"프롬프트 버전(시스템 프롬프트 해시): {', '.join(shas)}")
    if len(shas) > 1:
        L.append("")
        L.append("⚠️ **케이스마다 프롬프트 버전이 다르다.** 이어하기 사이에 프롬프트나 도구 명세가 바뀐 것이다. 이 수치는 한 조건의 값이 아니다.")
    L.append("")
    if report.aborted_reason:
        L += [f"⚠️ **중간에 멈춤**: {report.aborted_reason}. 아래 수치는 끝난 케이스만의 값이다. 같은 명령에 `--resume`을 붙여 이어서 실행한다.", ""]
    L += ["## 요약", "", f"평가된 케이스 {s['n_evaluated']}개 (사람 TB가 FAIL시키지 않아 제외 {s['n_not_failed']}, "
          f"동등 변형 제외 {s['n_equivalent_skipped']}, 미실행 {s['n_not_run']}).", "",
          "| 지표 | 값 |", "|---|---|",
          f"| 보고서를 낸 비율 | {_pct(s['report_rate'])} |",
          f"| 파일을 맞힘 | {_pct(s['file_accuracy'])} |",
          f"| **정확한 줄** | {_pct(s['exact_rate'])} |",
          f"| **정답 줄 ±{m.get('near')}줄 이내** | {_pct(s['located_rate'])} |",
          f"| 평균 단계 수 (보고서를 낸 케이스) | {_num(s['mean_steps_final'])} |",
          f"| 평균 도구 호출 수 | {_num(s['mean_tool_calls'])} |",
          f"| LLM 호출 (캐시 제외) / 캐시 | {s['llm_calls']} / {s['cached_calls']} |",
          f"| 형식 오류율 (단계 기준) | {_pct(s['format_error_rate'])} |",
          f"| 거부된 보고서 수 | {s['rejected_reports']} |",
          f"| STOP이 아닌 이유로 끝난 응답 수 (MAX_TOKENS 등) | {s['non_stop_steps']} |",
          f"| 빈 응답 재시도 (보냄 / 단계를 이어간 횟수) | {s['empty_retries']} / {s['empty_retries_recovered']} |",
          f"| 평탄한 도구 호출 정규화 (형식 오류였을 호출) | {s['normalized_calls']} |",
          f"| 토큰 입력 / 출력 | {s['input_tokens']} / {s['output_tokens']} |", ""]
    if s["tool_usage"]:
        L += ["### 도구 사용", "", "| 도구 | 호출 수 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in s["tool_usage"].items()]
        L += ["", f"로그·TB·파형 조회(`{'`, `'.join(EVIDENCE_TOOLS)}`)를 한 번이라도 쓴 케이스: "
                  f"{len(s['evidence_tool_cases'])}/{s['n_evaluated']}. 0에 가까우면 이 평가는 실패 시뮬레이션 디버깅이 아니라 "
                  "RTL 코드 리뷰 능력을 재고 있다.", ""]
    if s["n_fix_verified"]:
        fc = s["fix_categories"]
        L += ["### 수정안 검증 (7-5)", "",
              f"원본 사람 TB로 재시뮬레이션한 케이스 {s['n_fix_verified']}개. Agent가 rerun_sim을 직접 쓴 횟수 {s['agent_sim_runs']}.", "",
              "| 분류 | 개수 | 뜻 |", "|---|---|---|",
              f"| fixed_golden | {fc['fixed_golden']} | PASS, 골든 RTL과 같음 (원래 코드로 복원) |",
              f"| fixed_pass | {fc['fixed_pass']} | PASS이지만 골든과 다름 (대안 수정이거나 TB 구멍 — diff를 직접 확인) |",
              f"| still_fail | {fc['still_fail']} | 적용해도 FAIL |",
              f"| unverified | {fc['unverified']} | 적용/시뮬레이션 실패 |",
              f"| no_fix | {fc['no_fix']} | 보고서가 수정안을 지목하지 않음 |", "",
              f"위치는 맞혔는데(±줄 이내) 수정안이 없거나 실패한 케이스: {', '.join(s['located_but_not_fixed']) or '없음'}", ""]
    L += ["### 결과 분류", "", "| 분류 | 개수 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in s["categories"].items()] + [""]
    if s["by_type"]:
        L += ["### 버그 유형별", "", "| 유형 | 케이스 | ±줄 이내 | 정확 |", "|---|---|---|---|"]
        L += [f"| {t} | {v['n']} | {v['located']} | {v['exact']} |" for t, v in sorted(s["by_type"].items())] + [""]
    if s["confidence"]:
        L += ["### 확신도와 정답률 (보고서를 낸 케이스)", "", "| 확신도 | 케이스 | ±줄 이내 |", "|---|---|---|"]
        L += [f"| {k} | {v['n']} | {v['located']} |" for k, v in s["confidence"].items()]
        if s["high_conf_wrong"]:
            L += ["", f"⚠️ 확신도 high인데 틀린 케이스: {', '.join(s['high_conf_wrong'])}"]
        L.append("")
    L += ["## 케이스별", "", "| 버그 | 유형 | 정답 | Agent | 분류 | 수정안 | 상태 | 단계 | 호출 |", "|---|---|---|---|---|---|---|---|---|"]
    for c in report.cases:
        if c.outcome != "evaluated":
            L.append(f"| {c.bug_id} | {c.type} | - | - | {c.outcome} | - | {c.sim_status or '-'} | - | - |")
            continue
        loc = (c.run["report"] or {}).get("location") or {}
        got = f"{loc.get('file', '-')}:{loc.get('line', '-')}" if c.run["report"] else "-"
        L.append(f"| {c.bug_id} | {c.type} | {c.truth['file']}:{c.truth['line']} | {got} | {c.score['category']} | "
                 f"{c.fix['category'] if c.fix else '-'} | {c.run['status']} | {c.run['n_steps']} | {c.run['llm_calls']} |")
    L += ["", "## 해석할 때 주의", "",
          f"- 케이스가 {s['n_evaluated']}개뿐이고 버그는 한 줄 치환 단일 버그다. 비율은 통계가 아니라 이 세트에서의 관찰이다.",
          "- 정답 줄은 패치가 적용된 줄이다. 원인과 증상이 다른 줄이면 증상 줄을 지목해도 `near`/`wrong_line`이 된다.",
          "- 사람 TB가 쓴 신호 이름, 기대값 계산이 Agent에게 보이므로 LLM이 만든 TB의 실패에서는 결과가 다를 수 있다.",
          "- 수정안 PASS는 \"사람 TB가 못 잡는 오류가 없다\"는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 본다.",
          "- 같은 변형 세트로 TB 평가와 Agent 평가를 모두 했다. 세트에 맞춰 프롬프트를 고치면 이 수치는 낙관적이 된다."]
    return "\n".join(L) + "\n"
