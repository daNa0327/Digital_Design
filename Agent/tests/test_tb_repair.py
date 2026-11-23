"""TB Generator 6-3: 되먹임 재시도 루프 (FakeLLM + 가짜 컴파일 함수, Vivado/네트워크 불필요).

LLM 응답과 컴파일 결과를 우리가 정해 주고, 루프가 "언제 멈추고, 무엇을 되먹이는가"를 검증한다.
"""

import pytest

from core.compile_gate import CompileError, CompileResult
from core.rtl_summary import summarize_rtl
from core.tb_repair import (MAX_PROBLEMS, Attempt, GateRun, build_repair_prompt, collect_problems,
                            generate_with_gate)
from llm import DiskCache, FakeLLM, LLMClient, LLMResponse
from tests.test_tb_check import DUT, GOOD_TB


@pytest.fixture
def env(tmp_path):
    f = tmp_path / "counter.v"
    f.write_text(DUT)
    return summarize_rtl([f], top="counter"), {f.as_posix(): DUT}


def fenced(code: str) -> str:
    return f"```verilog\n{code}```"


def ok_compile():
    return CompileResult(ok=True, stage=None)


def bad_compile(line=None, code="VRFC 10-8885", msg="declarations are not allowed in an unnamed block", extra=()):
    errs = [CompileError("xvlog", code, msg, file="C:/x/tb.v", line=line)] + list(extra)
    return CompileResult(ok=False, stage="xvlog", errors=errs)


class Compiler:
    """차례대로 CompileResult를 돌려주고 받은 코드를 기록하는 가짜 compile_fn."""

    def __init__(self, results):
        self.results, self.codes, self.tops = list(results), [], []

    def __call__(self, code, top):
        self.codes.append(code)
        self.tops.append(top)
        return self.results[len(self.codes) - 1]


class LengthCut(FakeLLM):
    """finish_reason을 MAX_TOKENS로 돌려주는 가짜 LLM (응답이 잘린 상황)."""

    def generate(self, request):
        r = super().generate(request)
        return LLMResponse(text=r.text, model=r.model, finish_reason="MAX_TOKENS")


# ------------------------------------------------------------ 성공 경로
def test_first_attempt_success_stops_immediately(env):
    """첫 시도가 정적 검사와 컴파일을 모두 통과하면 LLM은 한 번만 부른다."""
    s, src = env
    fake, comp = FakeLLM([fenced(GOOD_TB)]), Compiler([ok_compile()])
    run = generate_with_gate(s, src, LLMClient(fake), comp)
    assert run.ok and len(run.attempts) == 1 and len(fake.calls) == 1 and len(comp.codes) == 1
    assert run.final.code.startswith("module tb_counter")


def test_compile_fn_receives_code_and_lets_gate_pick_top(env):
    """compile_fn에는 (코드, None)이 간다 - top 이름은 게이트가 코드에서 읽는다."""
    s, src = env
    comp = Compiler([ok_compile()])
    generate_with_gate(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)])), comp)
    assert comp.tops == [None] and comp.codes[0] == GOOD_TB


def test_compile_error_feeds_back_and_second_attempt_succeeds(env):
    """컴파일 실패 -> 수리 프롬프트로 재생성 -> 통과. 두 번째 프롬프트에 직전 코드와 에러와 줄이 들어간다."""
    s, src = env
    line_no = GOOD_TB.splitlines().index("  reg [3:0] m;") + 1
    fake = FakeLLM([fenced(GOOD_TB), fenced(GOOD_TB.replace("seed = 1;", "seed = 2;"))])
    comp = Compiler([bad_compile(line=line_no), ok_compile()])
    run = generate_with_gate(s, src, LLMClient(fake), comp)
    assert run.ok and len(run.attempts) == 2 and len(fake.calls) == 2
    second = fake.calls[1].prompt
    assert "## PREVIOUS ATTEMPT" in second and "reg [3:0] m;" in second     # 직전 코드
    assert "declarations are not allowed in an unnamed block" in second       # 에러 문구
    assert f"(line {line_no})" in second and "> reg [3:0] m;" in second       # 에러 줄의 코드
    assert "Declare `reg`/`integer`/`wire` at module level" in second          # 코드별 힌트
    assert "COMPLETE corrected testbench" in second


def test_repair_prompt_keeps_original_task_and_system(env):
    """수리 프롬프트는 원래 프롬프트(FACTS, 소스, 규약)를 그대로 포함하고 system도 같다."""
    s, src = env
    fake = FakeLLM([fenced(GOOD_TB), fenced(GOOD_TB)])
    generate_with_gate(s, src, LLMClient(fake), Compiler([bad_compile(), ok_compile()]))
    first, second = fake.calls
    assert second.prompt.startswith(first.prompt) and second.system == first.system
    assert "OUTPUT CONTRACT" in second.prompt


def test_attempts_record_compile_results_and_problems(env):
    """각 시도에 컴파일 결과와 문제 목록이 남는다 (성공한 시도는 문제 없음)."""
    s, src = env
    run = generate_with_gate(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)] * 2)), Compiler([bad_compile(), ok_compile()]))
    a1, a2 = run.attempts
    assert not a1.ok and a1.compile is not None and a1.problems
    assert a2.ok and a2.problems == []


# ------------------------------------------------------------ 정적 검사와 함께
def test_static_error_and_compile_error_are_fed_back_together(env):
    """정적 검사 error와 컴파일 에러를 한 번에 되먹여 라운드 수를 줄인다."""
    s, src = env
    bad_static = GOOD_TB.replace('$display("[TB] PASS")', '$display("done")')
    fake = FakeLLM([fenced(bad_static), fenced(GOOD_TB)])
    run = generate_with_gate(s, src, LLMClient(fake), Compiler([bad_compile(), ok_compile()]))
    second = fake.calls[1].prompt
    assert "[static:no_pass_marker]" in second and "[xvlog:VRFC 10-8885]" in second
    assert run.ok


def test_static_error_alone_prevents_ok_even_if_compile_passes(env):
    """컴파일이 통과해도 정적 error가 있으면 ok가 아니다 (PASS 마커 없는 TB는 평가에 못 씀)."""
    s, src = env
    bad_static = GOOD_TB.replace('$display("[TB] PASS")', '$display("done")')
    run = generate_with_gate(s, src, LLMClient(FakeLLM([fenced(bad_static)])), Compiler([ok_compile()]), max_attempts=1)
    assert not run.ok and run.attempts[0].problems[0].startswith("[static:no_pass_marker]")


def test_derived_compile_errors_are_not_fed_back(env):
    """'ignored due to previous errors' 같은 파생 에러는 되먹임에서 뺀다."""
    s, src = env
    derived = CompileError("xvlog", "VRFC 10-8530", "module 'tb_counter' is ignored due to previous errors",
                           primary=False)
    fake = FakeLLM([fenced(GOOD_TB), fenced(GOOD_TB)])
    generate_with_gate(s, src, LLMClient(fake), Compiler([bad_compile(extra=[derived]), ok_compile()]))
    assert "ignored due to previous errors" not in fake.calls[1].prompt


# ------------------------------------------------------------ 컴파일을 건너뛰는 경우
def test_response_without_code_skips_compile_and_says_so(env):
    """코드가 없는 응답은 컴파일하지 않고, 다음 프롬프트가 '쓸 만한 module이 없었다'고 알린다."""
    s, src = env
    fake, comp = FakeLLM(["죄송합니다.", fenced(GOOD_TB)]), Compiler([ok_compile()])
    run = generate_with_gate(s, src, LLMClient(fake), comp)
    assert len(comp.codes) == 1 and run.ok and run.attempts[0].compile is None
    assert "contained no usable module" in fake.calls[1].prompt


def test_truncated_response_skips_compile(env):
    """잘린 응답은 컴파일하지 않는다 (잘린 코드의 에러는 잡음)."""
    s, src = env
    comp = Compiler([])
    run = generate_with_gate(s, src, LLMClient(LengthCut([fenced(GOOD_TB)])), comp, max_attempts=1)
    assert comp.codes == [] and not run.ok and run.attempts[0].problems[0].startswith("[static:truncated]")


# ------------------------------------------------------------ 한도
def test_gives_up_after_max_attempts_and_keeps_every_attempt(env):
    """계속 실패하면 max_attempts번에서 멈추고 ok가 아니며, 모든 시도가 기록된다."""
    s, src = env
    fake = FakeLLM([fenced(GOOD_TB)] * 5)
    run = generate_with_gate(s, src, LLMClient(fake), Compiler([bad_compile()] * 5), max_attempts=3)
    assert not run.ok and len(run.attempts) == 3 and len(fake.calls) == 3 and run.max_attempts == 3
    assert [a.n for a in run.attempts] == [1, 2, 3]


def test_problem_list_is_capped(env):
    """문제가 아주 많아도 MAX_PROBLEMS개까지만 되먹인다."""
    s, src = env
    many = [CompileError("xvlog", f"VRFC 10-{i}", f"error {i}", line=None) for i in range(30)]
    comp = CompileResult(ok=False, stage="xvlog", errors=many)
    run = generate_with_gate(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)])), Compiler([comp]), max_attempts=1)
    assert len(run.attempts[0].problems) == MAX_PROBLEMS


def test_on_attempt_callback_is_called_for_each_attempt(env):
    """진행 표시용 콜백이 시도마다 호출된다."""
    s, src = env
    seen = []
    generate_with_gate(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)] * 2)), Compiler([bad_compile(), ok_compile()]),
                       on_attempt=lambda a: seen.append((a.n, a.ok)))
    assert seen == [(1, False), (2, True)]


def test_llm_calls_exclude_cached_attempts(env, tmp_path):
    """같은 입력을 다시 돌리면 모든 시도가 캐시에서 와서 실제 호출 수가 0이다 (무료 한도 절약)."""
    s, src = env
    cache = DiskCache(tmp_path / "c")
    fake = FakeLLM([fenced(GOOD_TB)] * 2)
    first = generate_with_gate(s, src, LLMClient(fake, cache=cache), Compiler([bad_compile(), ok_compile()]))
    again = generate_with_gate(s, src, LLMClient(fake, cache=cache), Compiler([bad_compile(), ok_compile()]))
    assert first.llm_calls == 2 and again.llm_calls == 0 and len(fake.calls) == 2


def test_gaterun_ok_is_false_when_empty():
    """시도가 없는 GateRun은 ok가 아니다."""
    assert not GateRun(attempts=[], max_attempts=3).ok


# ------------------------------------------------------------ 보조 함수
def test_collect_problems_handles_line_outside_code(env):
    """에러 줄 번호가 코드 범위를 벗어나도 죽지 않고 줄 인용만 생략한다."""
    s, src = env
    run = generate_with_gate(s, src, LLMClient(FakeLLM([fenced(GOOD_TB)])), Compiler([bad_compile(line=9999)]),
                             max_attempts=1)
    p = run.attempts[0].problems[0]
    assert "(line 9999)" in p and "\n      > " not in p


def test_collect_problems_without_compile_uses_static_only(env):
    """컴파일을 안 돌린 시도는 정적 error만 문제로 낸다."""
    s, src = env
    run = generate_with_gate(s, src, LLMClient(FakeLLM(["no code"])), Compiler([]), max_attempts=1)
    a = run.attempts[0]
    assert collect_problems(a.tb, None, a.tb.code) == ["[static:no_code] 응답에서 TB 코드를 찾지 못함"]


def test_build_repair_prompt_format():
    """수리 프롬프트는 원래 프롬프트, 직전 코드, 번호 붙은 문제, 전체 수정본 요구 순서다."""
    p = build_repair_prompt("ORIGINAL", "module a;\nendmodule\n", ["first", "second"])
    assert p.startswith("ORIGINAL")
    assert p.index("PREVIOUS ATTEMPT") < p.index("1. first") < p.index("2. second") < p.index("## TASK")
    assert "module a;\nendmodule" in p and "not a diff" in p