"""Phase 7-3: Debug Agent 루프 (가짜 LLM, Vivado/네트워크 불필요).

LLM의 응답을 우리가 정해 주고, 루프가 "언제 멈추고 무엇을 되먹이는가"를 검증한다.
실제 Gemini가 규약을 얼마나 잘 지키는지는 이 테스트의 범위가 아니다 (7-4에서 실측).
"""

import json

import pytest

from core.debug_loop import DebugRun, debug_loop, semantic_problems
from core.debug_protocol import evidence_from_log
from core.debug_tools import DebugWorkspace
from llm import BudgetExceeded, DailyQuotaExceeded, DiskCache, FakeLLM, LLMClient, LLMError

RTL = "\n".join(f"line{i}" for i in range(1, 11)) + "\n"          # 10줄
LOG = "CHECK_FAIL t=27 ns sig=count exp=3 got=4\nCHECKS total=10 mismatches=1\n[TB] FAIL: 1\n"


def tool(name, **args):
    return json.dumps({"thought": f"use {name}", "action": "tool", "tool": name, "args": args})


def final(**kw):
    rep = {"verdict": "rtl_bug", "location": {"file": "rtl/a.v", "line": 3}, "summary": "s", "root_cause": "c",
           "evidence": [{"step": 1, "observation": "saw it"}], "fix_proposal_ids": [], "confidence": "high"}
    rep.update(kw)
    return json.dumps({"thought": "done", "action": "final", "report": rep})


@pytest.fixture
def ws():
    return DebugWorkspace({"rtl/a.v": RTL}, {"tb/t.v": "x\n"}, LOG)


def ev(ws):
    return evidence_from_log("m", "FAIL", "FAIL", ws.log, ws.list_files())


def run(ws, responses, **kw):
    fake = FakeLLM(responses)
    return debug_loop(ws, ev(ws), LLMClient(fake), **kw), fake


# ---------------------------------------------------------------------------------------------
# 정상 흐름
# ---------------------------------------------------------------------------------------------
def test_도구_호출_후_보고서로_종료(ws):
    """도구 1번 -> final. 상태는 final, 단계 2개, LLM 호출 2회, 보고서가 그대로 나온다."""
    r, fake = run(ws, [tool("read_rtl", file="rtl/a.v"), final()])
    assert r.status == "final" and r.n_steps == 2 and r.n_tool_calls == 1 and r.llm_calls == 2
    assert r.report["location"] == {"file": "rtl/a.v", "line": 3}
    assert [s.kind for s in r.steps] == ["tool", "final"]
    assert len(fake.calls) == 2


def test_관측이_다음_프롬프트에_누적된다(ws):
    """두 번째 호출의 프롬프트에 첫 도구 호출과 그 결과(줄 내용)가 들어 있다. 시스템 프롬프트도 매번 전달된다."""
    r, fake = run(ws, [tool("read_rtl", file="rtl/a.v", start_line=2, end_line=3), final()])
    p2 = fake.calls[1].prompt
    assert "## Step 1" in p2 and "line2" in p2 and "line3" in p2
    assert "## Step 1" not in fake.calls[0].prompt
    assert all(c.system and "debugging agent" in c.system for c in fake.calls)


def test_도구_오류는_루프를_죽이지_않는다(ws):
    """없는 파일을 읽어도 오류가 관측으로 돌아가고 Agent가 계속한다 (후보 목록을 보고 고칠 수 있다)."""
    r, fake = run(ws, [tool("read_rtl", file="a.v"), tool("read_rtl", file="rtl/a.v"), final(
        evidence=[{"step": 2, "observation": "ok"}])])
    assert r.status == "final"
    assert '"available": ["rtl/a.v"]' in fake.calls[1].prompt


def test_TB_수정_제안은_거부되고_루프는_계속(ws):
    """TB에 propose_fix를 호출하면 거부 메시지가 관측으로 가고, tb_issue 보고를 안내한다."""
    r, fake = run(ws, [tool("propose_fix", file="tb/t.v", find="x", replace="y"),
                       final(verdict="tb_issue", location=None)])
    assert r.status == "final" and r.proposals == []
    assert "tb_issue" in fake.calls[1].prompt


def test_수정안은_결과에_담긴다(ws):
    """propose_fix가 저장한 수정안은 DebugRun.proposals에 나오고, 보고서가 그 id를 인용할 수 있다."""
    r, _ = run(ws, [tool("propose_fix", file="rtl/a.v", find="line3\n", replace="LINE3\n", rationale="r"),
                    final(fix_proposal_ids=[1], evidence=[{"step": 1, "observation": "diff"}])])
    assert r.status == "final" and r.proposals[0]["id"] == 1 and r.proposals[0]["line"] == 3


# ---------------------------------------------------------------------------------------------
# 형식 오류
# ---------------------------------------------------------------------------------------------
def test_형식_오류_후_복구(ws):
    """JSON이 아닌 응답은 이유와 함께 되먹임되고, 다음 응답이 올바르면 계속한다. 형식 오류도 단계를 쓴다."""
    r, fake = run(ws, ["그냥 문장", tool("read_rtl", file="rtl/a.v"), final(evidence=[{"step": 2, "observation": "o"}])])
    assert r.status == "final" and r.format_errors == 1 and r.n_steps == 3
    assert "FORMAT ERROR" in fake.calls[1].prompt and "찾지 못" in fake.calls[1].prompt


def test_연속_형식_오류는_중단(ws):
    """연속 3회(기본)면 더 호출하지 않고 format_errors로 끝낸다 (무한 낭비 방지)."""
    r, fake = run(ws, ["a", "b", "c", final()])
    assert r.status == "format_errors" and r.report is None and len(fake.calls) == 3


def test_형식_오류_카운트는_성공하면_초기화(ws):
    """오류가 연속이 아니면 누적 한도에 걸리지 않는다 (오류-성공-오류-성공-오류)."""
    r, _ = run(ws, ["x", tool("read_rtl", file="rtl/a.v"), "y", tool("read_rtl", file="rtl/a.v", start_line=2),
                    "z", final(evidence=[{"step": 2, "observation": "o"}])], max_steps=8)
    assert r.status == "final" and r.format_errors == 3


# ---------------------------------------------------------------------------------------------
# 보고서 거부
# ---------------------------------------------------------------------------------------------
def test_도구를_안_부르고_결론내면_거부(ws):
    """근거로 쓸 단계가 하나도 없으면(도구 호출 0회) rtl_bug 보고는 거부되고 이유가 되먹임된다."""
    r, fake = run(ws, [final(), tool("read_rtl", file="rtl/a.v"), final(evidence=[{"step": 2, "observation": "o"}])])
    assert r.status == "final" and r.rejected_reports == 1
    assert "도구를 호출한 단계가 아니다" in fake.calls[1].prompt


def test_형식오류_단계를_근거로_인용하면_거부(ws):
    """형식 오류로 날린 단계(도구를 부르지 않음)를 근거로 인용한 지어낸 보고서를 막는다."""
    r, _ = run(ws, ["bad", tool("read_rtl", file="rtl/a.v"),
                    final(evidence=[{"step": 1, "observation": "o"}]),          # 1단계는 형식 오류
                    final(evidence=[{"step": 2, "observation": "o"}])])
    assert r.status == "final" and r.rejected_reports == 1


def test_없는_줄_번호는_거부(ws):
    """RTL이 10줄인데 40번 줄을 지목하면 거부한다 (존재하지 않는 위치 환각)."""
    r, fake = run(ws, [tool("read_rtl", file="rtl/a.v"), final(location={"file": "rtl/a.v", "line": 40}),
                       final()])
    assert r.status == "final" and r.rejected_reports == 1 and r.report["location"]["line"] == 3
    assert "길이(10줄)" in fake.calls[2].prompt


def test_없는_수정안_id는_거부(ws):
    """propose_fix를 부르지 않았는데 수정안 id를 인용하면 거부한다."""
    r, _ = run(ws, [tool("read_rtl", file="rtl/a.v"), final(fix_proposal_ids=[7]), final(fix_proposal_ids=[])])
    assert r.status == "final" and r.rejected_reports == 1


def test_unknown_보고서는_근거없이_수락(ws):
    """증거가 부족하면 unknown으로 끝낼 수 있다 (억지로 결론을 짓게 하지 않는다)."""
    rep = {"verdict": "unknown", "summary": "s", "root_cause": "VCD가 없어 확인 불가", "confidence": "low"}
    r, _ = run(ws, [json.dumps({"action": "final", "report": rep})])
    assert r.status == "final" and r.report["verdict"] == "unknown" and r.n_steps == 1


# ---------------------------------------------------------------------------------------------
# 단계 제한
# ---------------------------------------------------------------------------------------------
def test_단계를_다_쓰면_max_steps(ws):
    """도구만 계속 부르면 max_steps에서 끝나고 보고서는 None이다. 억지로 만들어 내지 않는다."""
    resp = [tool("read_rtl", file="rtl/a.v", start_line=i) for i in range(1, 6)]
    r, fake = run(ws, resp, max_steps=3)
    assert r.status == "max_steps" and r.report is None and r.n_steps == 3 and len(fake.calls) == 3


def test_마지막_단계에서는_종료를_요구한다(ws):
    """남은 단계가 1이면 프롬프트가 'LAST step'을 알려서 보고서를 내도록 유도한다."""
    r, fake = run(ws, [tool("read_rtl", file="rtl/a.v"), final()], max_steps=2)
    assert "LAST step" not in fake.calls[0].prompt and "LAST step" in fake.calls[1].prompt
    assert "[1 step(s) left" in fake.calls[1].prompt


def test_같은_호출_반복은_알려준다(ws):
    """같은 도구를 같은 인자로 다시 부르면 이전 단계를 알려 준다 (같은 확인 반복 방지)."""
    r, fake = run(ws, [tool("read_rtl", file="rtl/a.v"), tool("read_rtl", file="rtl/a.v"), final()])
    assert "step 1에서 같은 도구를 같은 인자로 이미 호출했다" in fake.calls[2].prompt
    assert '"lines"' in fake.calls[2].prompt                        # 결과 자체는 여전히 돌려준다


# ---------------------------------------------------------------------------------------------
# LLM 오류
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("exc,status", [
    (DailyQuotaExceeded("일일 한도"), "quota"), (BudgetExceeded("상한"), "budget"), (LLMError("boom"), "llm_error")])
def test_LLM_오류는_종류별_상태로_끝나고_지금까지의_기록은_남는다(ws, exc, status):
    """호출이 실패해도 예외로 터지지 않고 상태와 이유를 남기며, 이전 단계의 기록과 수정안은 유지된다."""
    r, _ = run(ws, [tool("read_rtl", file="rtl/a.v"), exc])
    assert r.status == status and r.report is None and r.n_steps == 1 and r.error


# ---------------------------------------------------------------------------------------------
# 캐시와 기록
# ---------------------------------------------------------------------------------------------
def test_같은_입력_재실행은_호출을_쓰지_않는다(ws, tmp_path):
    """디스크 캐시 덕분에 같은 사건을 다시 돌리면 실제 호출은 0회이고 결과는 같다 (프롬프트가 결정적이기 때문)."""
    script = [tool("read_rtl", file="rtl/a.v"), final()]
    c1 = LLMClient(FakeLLM(script), cache=DiskCache(tmp_path / "c"))
    r1 = debug_loop(ws, ev(ws), c1)
    ws2 = DebugWorkspace({"rtl/a.v": RTL}, {"tb/t.v": "x\n"}, LOG)
    fake2 = FakeLLM([])
    r2 = debug_loop(ws2, ev(ws2), LLMClient(fake2, cache=DiskCache(tmp_path / "c")))
    assert (r1.llm_calls, r1.cached_calls) == (2, 0) and (r2.llm_calls, r2.cached_calls) == (0, 2)
    assert r2.report == r1.report and fake2.calls == []


def test_on_step_콜백과_to_dict(ws):
    """진행 상황 콜백이 단계마다 불리고, 결과는 JSON으로 저장할 수 있다."""
    seen = []
    r, _ = run(ws, [tool("read_rtl", file="rtl/a.v"), final()], on_step=seen.append)
    assert [s.kind for s in seen] == ["tool", "final"]
    d = json.loads(json.dumps(r.to_dict()))
    assert d["status"] == "final" and d["n_tool_calls"] == 1 and len(d["turns"]) == 2


def test_토큰과_모델_인자가_전달된다(ws):
    """온도 0, 최대 출력 토큰, 모델 지정이 요청에 그대로 실린다."""
    r, fake = run(ws, [final(evidence=[])], max_output_tokens=777, model="m-x")
    assert fake.calls[0].temperature == 0.0 and fake.calls[0].max_output_tokens == 777
    assert fake.calls[0].model == "m-x"


# ---------------------------------------------------------------------------------------------
# semantic_problems 단독
# ---------------------------------------------------------------------------------------------
def test_semantic_problems_단독(ws):
    """줄 번호 범위와 수정안 id 검사를 따로 확인한다."""
    ok = {"verdict": "rtl_bug", "location": {"file": "rtl/a.v", "line": 10}, "fix_proposal_ids": []}
    assert semantic_problems(ok, ws, set()) == []
    assert semantic_problems({**ok, "location": {"file": "rtl/a.v", "line": 11}}, ws, set())
    assert semantic_problems({**ok, "fix_proposal_ids": [1]}, ws, set())