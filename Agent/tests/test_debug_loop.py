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
    """JSON이 아닌 응답은 이유와 함께 되먹임되고, 다음 응답이 올바르면 계속한다. 형식 오류 턴도 턴 번호는 받는다."""
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


# ---------------------------------------------------------------------------------------------
# finish_reason 기록 (실측 1차: 빈 응답과 잘린 JSON의 원인을 가리기 위함)
# ---------------------------------------------------------------------------------------------
def test_finish_reason이_단계마다_기록된다(ws):
    """응답이 어떤 이유로 끝났는지(STOP, MAX_TOKENS 등)를 단계 기록에 남긴다."""
    r, _ = run(ws, [(tool("read_rtl", file="rtl/a.v"), "STOP"), (final(evidence=[{"step": 1, "observation": "o"}]), "STOP")])
    assert [s.finish_reason for s in r.steps] == ["STOP", "STOP"]


def test_잘린_응답의_형식_오류_안내에_finish_reason이_표시된다(ws):
    """MAX_TOKENS로 잘려 JSON이 깨진 응답은 형식 오류로 처리하되, 기록에 원인(finish_reason)을 남긴다.
    STOP인 형식 오류에는 붙이지 않는다."""
    cut = '{"action": "final", "report": {"verdict": "rtl_bug", '
    r, _ = run(ws, [(cut, "MAX_TOKENS"), ("그냥 문장", "STOP"), (tool("read_rtl", file="rtl/a.v"), "STOP"),
                    final(evidence=[{"step": 3, "observation": "o"}])], max_steps=6)
    assert r.steps[0].kind == "format_error" and "finish_reason=MAX_TOKENS" in r.steps[0].note
    assert r.steps[1].kind == "format_error" and "finish_reason" not in r.steps[1].note
    assert r.steps[0].finish_reason == "MAX_TOKENS" and r.status == "final"


def test_finish_reason은_to_dict에_저장된다(ws):
    """사후 분석을 위해 결과 JSON의 steps에 finish_reason이 들어간다."""
    r, _ = run(ws, [(tool("read_rtl", file="rtl/a.v"), "MAX_TOKENS"), final(evidence=[{"step": 1, "observation": "o"}])])
    d = json.loads(json.dumps(r.to_dict()))
    assert d["steps"][0]["finish_reason"] == "MAX_TOKENS"


# ---------------------------------------------------------------------------------------------
# 사후 분석을 위한 기록: 처음 받은 메시지와 프롬프트 버전 (B15 분석 중 확인된 공백)
# ---------------------------------------------------------------------------------------------
def test_처음_받은_메시지와_프롬프트_해시가_결과에_남는다(ws):
    """Agent가 처음에 무엇을 알았는지(첫 실패 로그 등)를 나중에 볼 수 있어야 한다. 이전에는 대화에서 빠져 있었다."""
    r, _ = run(ws, [tool("read_rtl", file="rtl/a.v"), final(evidence=[{"step": 1, "observation": "o"}])])
    d = json.loads(json.dumps(r.to_dict()))
    assert "# Failure report" in d["initial_message"] and "sig=count" in d["initial_message"]
    assert len(d["prompt_sha"]) == 12 and int(d["prompt_sha"], 16) >= 0


def test_프롬프트_해시는_같은_조건이면_같고_도구_명세가_바뀌면_달라진다(ws):
    """같은 시스템 프롬프트는 같은 해시, VCD 도구가 추가되면 다른 해시 (결과가 어떤 프롬프트의 것인지 구분)."""
    class FakeVcd:
        pass

    r1, _ = run(ws, [final(evidence=[])])
    r2, _ = run(DebugWorkspace({"rtl/a.v": RTL}, {"tb/t.v": "x\n"}, LOG), [final(evidence=[])])
    r3, _ = run(DebugWorkspace({"rtl/a.v": RTL}, {"tb/t.v": "x\n"}, LOG, vcd=FakeVcd()), [final(evidence=[])])
    assert r1.prompt_sha == r2.prompt_sha != r3.prompt_sha


# ---------------------------------------------------------------------------------------------
# 빈 응답 재시도 (v0b: 22건의 비STOP 응답 전부 MALFORMED_FUNCTION_CALL, 그중 일부는 빈 응답이라 B10은 추론 없이 끝났다)
# ---------------------------------------------------------------------------------------------
EMPTY = ("", "MALFORMED_FUNCTION_CALL")


def test_빈_응답은_같은_요청을_다시_보내고_단계로_세지_않는다(ws):
    """첫 응답이 비면 같은 프롬프트를 한 번 더 보낸다. 정상 응답을 받으면 형식 오류도, 단계 소모도 없다."""
    r, fake = run(ws, [EMPTY, tool("read_rtl", file="rtl/a.v"), final()])
    assert r.status == "final" and r.format_errors == 0 and r.n_steps == 2
    assert r.empty_retries == 1 and r.llm_calls == 3                  # 재시도도 호출 수에는 들어간다
    assert fake.calls[0].prompt == fake.calls[1].prompt               # 같은 요청 (모델이 이전 실패를 보지 않는다)
    assert "FORMAT ERROR" not in fake.calls[1].prompt and "FORMAT ERROR" not in fake.calls[2].prompt
    s = r.steps[0]
    assert (s.kind, s.retries, s.retry_reasons) == ("tool", 1, ["MALFORMED_FUNCTION_CALL"])
    assert r.steps[1].retries == 0


def test_재시도해도_비면_형식_오류로_처리하고_계속한다(ws):
    """두 번 다 비면 기존처럼 형식 오류 한 단계로 기록하고 오류 메시지를 되먹인다. 재시도 횟수는 그 단계에 남는다."""
    r, fake = run(ws, [EMPTY, EMPTY, tool("read_rtl", file="rtl/a.v"),
                       final(evidence=[{"step": 2, "observation": "saw it"}])])     # 1단계는 형식 오류라 근거가 될 수 없다
    assert r.status == "final" and r.format_errors == 1 and r.n_steps == 3
    assert [s.kind for s in r.steps] == ["format_error", "tool", "final"]
    assert r.steps[0].retries == 1 and "비어 있다" in r.steps[0].note
    assert r.empty_retries == 1 and r.llm_calls == 4
    assert "FORMAT ERROR" in fake.calls[2].prompt


def test_empty_retries가_0이면_재시도하지_않는다(ws):
    """옵션으로 끌 수 있다. 빈 응답이 곧바로 형식 오류가 된다 (v0b와 같은 동작)."""
    r, fake = run(ws, [EMPTY, tool("read_rtl", file="rtl/a.v"), final(evidence=[{"step": 2, "observation": "o"}])],
                  empty_retries=0)
    assert r.status == "final" and r.format_errors == 1 and r.empty_retries == 0 and r.llm_calls == 3 and r.n_steps == 3
    assert r.steps[0].retries == 0


def test_빈_응답이_계속되면_재시도해도_연속_형식_오류_한도로_끝난다(ws):
    """B10처럼 계속 비는 경우: 단계마다 재시도 1번씩 하고, 3단계 연속 실패하면 format_errors로 끝난다. 무한히 재시도하지 않는다."""
    r, fake = run(ws, [EMPTY] * 6)
    assert r.status == "format_errors" and r.format_errors == 3 and r.n_steps == 3
    assert r.empty_retries == 3 and r.llm_calls == 6 and len(fake.calls) == 6


def test_재시도도_호출_상한에_포함된다(ws):
    """max_calls=2일 때 첫 호출 + 재시도로 상한을 다 쓰고, 다음 단계에서 budget으로 끝난다 (몰래 호출하지 않는다)."""
    fake = FakeLLM(["", ""])
    r = debug_loop(ws, ev(ws), LLMClient(fake, max_calls=2))
    assert r.status == "budget" and r.empty_retries == 1 and r.llm_calls == 2 and len(fake.calls) == 2
    assert r.steps[0].kind == "format_error"


def test_재시도_중_쿼터가_소진되면_quota로_끝난다(ws):
    """재시도 호출이 일일 한도 예외를 만나면 그 단계를 기록하지 않고 quota로 끝난다 (이어하기 대상)."""
    fake = FakeLLM([EMPTY, DailyQuotaExceeded("일일 한도")])
    r = debug_loop(ws, ev(ws), LLMClient(fake))
    assert r.status == "quota" and r.n_steps == 0 and r.empty_retries == 1


def test_빈_응답은_캐시에_남지_않아_재시도가_새_응답을_받고_다음_실행은_재생한다(ws, tmp_path):
    """캐시를 켠 상태에서도 재시도가 효과가 있다 (빈 응답이 저장되어 있으면 같은 빈 응답이 재생된다).
    정상 응답은 저장되어 같은 프롬프트의 다음 실행에서 호출 없이 재생된다."""
    cache = DiskCache(tmp_path)
    f1 = FakeLLM([EMPTY, tool("read_rtl", file="rtl/a.v"), final()])
    r1 = debug_loop(ws, ev(ws), LLMClient(f1, cache=cache))
    assert r1.status == "final" and r1.llm_calls == 3 and r1.cached_calls == 0 and r1.empty_retries == 1
    f2 = FakeLLM([])
    r2 = debug_loop(ws, ev(ws), LLMClient(f2, cache=cache))
    assert r2.status == "final" and r2.llm_calls == 0 and r2.cached_calls == 2 and r2.empty_retries == 0
    assert f2.calls == []


def test_재시도_정보가_JSON에_저장된다(ws):
    """결과 JSON에서 어느 단계가 재시도됐고 버려진 응답의 finish_reason이 무엇이었는지 볼 수 있다."""
    r, _ = run(ws, [EMPTY, tool("read_rtl", file="rtl/a.v"), final()])
    d = json.loads(json.dumps(r.to_dict()))
    assert d["empty_retries"] == 1
    assert d["steps"][0]["retries"] == 1 and d["steps"][0]["retry_reasons"] == ["MALFORMED_FUNCTION_CALL"]


def test_평탄한_propose_fix_호출은_단계를_잃지_않고_집계된다(ws):
    """v0c B16: `"action":"propose_fix"` 평탄 호출이 형식 오류가 되어 마지막 단계와 겹쳐 수정안 없이 끝났다.
    정규화하면 형식 오류가 아니라 정상 도구 호출이고, 수정안이 저장되며 normalized_calls로 센다."""
    flat = json.dumps({"thought": "fix", "action": "propose_fix", "file": "rtl/a.v",
                       "find": "line3", "replace": "LINE3", "rationale": "r"})
    r, fake = run(ws, [flat, final(fix_proposal_ids=[1], evidence=[{"step": 1, "observation": "o"}])])
    assert r.status == "final" and r.format_errors == 0 and r.normalized_calls == 1
    assert r.steps[0].kind == "tool" and r.steps[0].tool == "propose_fix" and "정규화" in r.steps[0].note
    assert len(r.proposals) == 1 and r.to_dict()["normalized_calls"] == 1
    assert '"action": "tool"' in fake.calls[1].prompt and '"tool": "propose_fix"' in fake.calls[1].prompt


# ---------------------------------------------------------------------------------------------
# F1: 형식 오류와 거부된 보고서는 조사 단계로 세지 않는다
# ---------------------------------------------------------------------------------------------
def test_형식_오류는_조사_단계를_쓰지_않는다(ws):
    """형식 오류 뒤에도 남은 단계가 그대로다. max_steps=2에서 형식 오류 1번 + 도구 2번을 할 수 있다."""
    r, fake = run(ws, ["bad", tool("read_rtl", file="rtl/a.v"), tool("read_rtl", file="rtl/a.v", start_line=2)],
                  max_steps=2)
    assert "[2 step(s) left" in fake.calls[0].prompt and "[2 step(s) left" in fake.calls[1].prompt
    assert r.n_tool_calls == 2 and r.status == "max_steps" and len(fake.calls) == 3


def test_거부된_보고서는_조사_단계를_쓰지_않는다(ws):
    """마지막 단계에서 낸 보고서가 거부돼도 고친 보고서를 낼 기회가 남는다."""
    r, fake = run(ws, [tool("read_rtl", file="rtl/a.v"),
                       final(evidence=[{"step": 9, "observation": "o"}]),       # 없는 단계 인용 -> 거부
                       final()], max_steps=2)
    assert r.status == "final" and r.rejected_reports == 1
    assert "LAST step" in fake.calls[1].prompt and "LAST step" in fake.calls[2].prompt


def test_세지_않는_턴은_max_free_turns로_상한이_있다(ws):
    """거부만 반복하면 max_steps + max_free_turns 턴에서 끝난다 (호출량 상한 유지)."""
    r, fake = run(ws, [final()] * 10, max_steps=2, max_free_turns=2)
    assert r.status == "max_steps" and r.report is None and len(fake.calls) == 4 and r.rejected_reports == 4
