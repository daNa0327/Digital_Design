"""TB Generator 6-2: generate_tb (FakeLLM으로 호출 없이 검증).

LLM 응답을 우리가 정해 주고, 추출 -> 정적 검사 -> 결과 객체가 기대대로 만들어지는지 본다.
"""

import pytest

from core.rtl_summary import summarize_rtl
from core.tb_generator import TBResult, generate_tb, render_tb_file, save_tb
from core.tb_prompt import TBPromptError
from llm import DiskCache, FakeLLM, LLMClient, LLMResponse
from tests.test_tb_check import DUT, GOOD_TB


@pytest.fixture
def env(tmp_path):
    """(summary, sources) 카운터 DUT."""
    f = tmp_path / "counter.v"
    f.write_text(DUT)
    return summarize_rtl([f], top="counter"), {f.as_posix(): DUT}


def fenced(code: str) -> str:
    return f"설명\n```verilog\n{code}```\n"


class LengthCut(FakeLLM):
    """응답이 길이 제한으로 끊긴 것처럼 finish_reason을 MAX_TOKENS로 돌려주는 가짜 LLM."""

    def generate(self, request):
        r = super().generate(request)
        return LLMResponse(text=r.text, model=r.model, finish_reason="MAX_TOKENS")


def test_good_response_is_ok(env):
    """규약을 지킨 응답은 ok이고 코드가 추출된다."""
    s, src = env
    r = generate_tb(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)])))
    assert r.ok and r.code.startswith("module tb_counter") and r.tb_name == "tb_counter"
    assert [i for i in r.issues if i.level == "error"] == []


def test_request_carries_prompt_system_and_settings(env):
    """LLM에 가는 요청에 system, 프롬프트, 온도 0, 출력 상한이 실린다."""
    s, src = env
    fake = FakeLLM([fenced(GOOD_TB)])
    generate_tb(s, src, LLMClient(fake), max_output_tokens=4096)
    req = fake.calls[0]
    assert "verification engineer" in req.system and "## FACTS" in req.prompt
    assert req.temperature == 0.0 and req.max_output_tokens == 4096


def test_spec_text_reaches_the_prompt(env):
    """명세는 프롬프트에 실려 LLM에 전달된다."""
    s, src = env
    fake = FakeLLM([fenced(GOOD_TB)])
    generate_tb(s, src, LLMClient(fake), spec_text="SPEC-MARKER-123")
    assert "SPEC-MARKER-123" in fake.calls[0].prompt


def test_bad_tb_is_not_ok_and_reports_errors(env):
    """규약 위반 TB는 ok가 아니고, 사유가 issues에 남는다 (코드는 디버깅용으로 보존)."""
    s, src = env
    bad = GOOD_TB.replace('$display("[TB] PASS")', '$display("done")')
    r = generate_tb(s, src, LLMClient(FakeLLM([fenced(bad)])))
    assert not r.ok and r.code
    assert "no_pass_marker" in {i.code for i in r.issues}


def test_response_without_code_is_not_ok(env):
    """코드가 없는 응답은 no_code 에러이고 코드는 빈 문자열이다."""
    s, src = env
    r = generate_tb(s, src, LLMClient(FakeLLM(["죄송합니다, 만들 수 없습니다."])))
    assert not r.ok and r.code == "" and {i.code for i in r.issues} == {"no_code"}


def test_truncated_response_is_flagged_first(env):
    """finish_reason이 STOP이 아니면 truncated 에러가 첫 번째 문제로 붙는다."""
    s, src = env
    r = generate_tb(s, src, LLMClient(LengthCut([fenced(GOOD_TB)])))
    assert not r.ok and r.issues[0].code == "truncated"


def test_enum_style_stop_reason_is_accepted(env):
    """finish_reason이 'FinishReason.STOP' 꼴이어도 정상 종료로 본다."""
    s, src = env

    class EnumStyle(FakeLLM):
        def generate(self, request):
            r = super().generate(request)
            return LLMResponse(text=r.text, model=r.model, finish_reason="FinishReason.STOP")

    assert generate_tb(s, src, LLMClient(EnumStyle([fenced(GOOD_TB)]))).ok


def test_result_records_model_tokens_and_prompt_hash(env):
    """결과에 모델, 토큰 수, 프롬프트 해시가 남고, 같은 입력은 같은 해시다."""
    s, src = env
    a = generate_tb(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)], model="m-x")))
    b = generate_tb(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)])))
    assert a.model == "m-x" and a.input_tokens > 0 and a.output_tokens > 0
    assert len(a.prompt_sha) == 12 and a.prompt_sha == b.prompt_sha


def test_prompt_hash_changes_with_spec(env):
    """명세가 달라지면 프롬프트 해시도 달라진다."""
    s, src = env
    a = generate_tb(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)])), spec_text="A")
    b = generate_tb(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)])), spec_text="B")
    assert a.prompt_sha != b.prompt_sha


def test_extract_notes_are_kept(env):
    """펜스 없이 답했다는 사실이 extract_notes에 남는다."""
    s, src = env
    r = generate_tb(s, src, LLMClient(FakeLLM([GOOD_TB])))
    assert r.ok and any("펜스" in n for n in r.extract_notes)


def test_unready_summary_raises_before_calling_llm(env):
    """TB를 만들 수 없는 요약이면 LLM을 부르지 않고 TBPromptError를 던진다."""
    s, src = env
    s["ready_for_tb"], s["blockers"] = False, ["사유"]
    fake = FakeLLM([fenced(GOOD_TB)])
    with pytest.raises(TBPromptError):
        generate_tb(s, src, LLMClient(fake))
    assert fake.calls == []


def test_same_request_hits_cache_and_skips_second_call(env, tmp_path):
    """같은 입력으로 다시 생성하면 캐시에서 오고 제공자를 다시 부르지 않는다 (무료 호출량 절약)."""
    s, src = env
    fake = FakeLLM([fenced(GOOD_TB)])
    client = LLMClient(fake, cache=DiskCache(tmp_path / "cache"))
    first = generate_tb(s, src, client)
    second = generate_tb(s, src, client)
    assert not first.cached and second.cached and len(fake.calls) == 1
    assert second.code == first.code


def test_render_adds_traceability_header(env):
    """저장되는 파일에는 DUT, 모델, 프롬프트 해시가 머리말 주석으로 붙고, 코드 본문은 그대로다."""
    s, src = env
    r = generate_tb(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)], model="m-x")))
    text = render_tb_file(r)
    assert text.startswith("// Generated by") and "dut=counter" in text and "model=m-x" in text
    assert f"prompt_sha={r.prompt_sha}" in text and text.endswith(r.code)


def test_save_creates_folders_and_writes_file(env, tmp_path):
    """저장 경로의 상위 폴더가 없어도 만들어 쓴다."""
    s, src = env
    r = generate_tb(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)])))
    p = save_tb(r, tmp_path / "a" / "b" / "tb.v")
    assert p.read_text(encoding="utf-8").endswith(r.code)


def test_saved_file_with_header_still_passes_checker(env, tmp_path):
    """머리말 주석이 붙은 저장본도 검사기를 그대로 통과한다 (주석은 검사에서 무시됨)."""
    from core.tb_check import check_tb, has_errors
    s, src = env
    r = generate_tb(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)])))
    saved = save_tb(r, tmp_path / "tb.v").read_text(encoding="utf-8")
    assert not has_errors(check_tb(saved, s))


def test_tbresult_ok_requires_code():
    """코드가 비어 있으면 issues가 없어도 ok가 아니다."""
    r = TBResult(top="t", tb_name="tb_t", code="", issues=[], raw_text="", model="m", prompt_sha="x")
    assert not r.ok
