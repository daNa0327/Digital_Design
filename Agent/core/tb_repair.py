"""TB Generator 6-3: 정적 검사와 컴파일 에러를 LLM에 되먹여 TB를 고치는 재시도 루프.

한 번에 맞는 TB가 나오지 않는 것을 전제로 한다 (실제로 첫 생성에서 `reg`를 이름 없는 블록에 선언해 xvlog가 거부했음).
  생성 -> 정적 검사 -> 컴파일 게이트 -> (실패) 문제 목록을 담은 수리 프롬프트 -> 재생성 ... 최대 N회
LLM 호출은 시도마다 1회, 컴파일은 결정적이라 호출량을 쓰지 않는다.

공개 API:
    generate_with_gate(summary, sources, client, compile_fn, spec_text=None, max_attempts=3, ...) -> GateRun
    build_repair_prompt(original_prompt, code, problems) -> str
    collect_problems(tb, compile_result, code) -> list[str]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from core.compile_gate import CompileResult
from core.tb_check import errors_of
from core.tb_generator import TBResult, result_from_response
from core.tb_prompt import build_tb_prompt
from llm.base import LLMRequest

MAX_PROBLEMS = 8                   # 한 번에 되먹이는 문제 수 상한 (많으면 LLM이 헷갈리고 토큰만 늘어남)

# 자주 나오는 에러 코드별 한 줄 힌트 (LLM이 같은 실수를 반복하지 않도록)
_HINTS = {
    "VRFC 10-8885": "Declare `reg`/`integer`/`wire` at module level, or inside a NAMED block (`begin : name`). "
                    "Unnamed begin/end blocks cannot contain declarations in Verilog-2001.",
    "VRFC 10-2063": "A module or instance name could not be resolved. Instantiate only the DUT module named in FACTS.",
    "VRFC 10-3236": "A signal is used before it is declared. Declare every signal before its first use.",
}


@dataclass
class Attempt:
    n: int                                   # 1부터
    tb: TBResult
    compile: CompileResult | None            # 컴파일을 돌리지 않았으면 None (코드 없음/잘림)
    problems: list[str] = field(default_factory=list)   # 이 시도에서 나온 문제 (다음 프롬프트에 들어감)

    @property
    def ok(self) -> bool:
        return self.tb.ok and self.compile is not None and self.compile.ok


@dataclass
class GateRun:
    attempts: list[Attempt]
    max_attempts: int

    @property
    def ok(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].ok

    @property
    def final(self) -> TBResult:
        return self.attempts[-1].tb

    @property
    def llm_calls(self) -> int:
        """실제 제공자 호출 수 (캐시에서 온 시도는 제외)."""
        return sum(1 for a in self.attempts if not a.tb.cached)


# ---------------------------------------------------------------- 문제 목록
def collect_problems(tb: TBResult, comp: CompileResult | None, code: str) -> list[str]:
    """정적 검사 error와 컴파일 에러를 번호 매길 문장으로 모은다. 컴파일 에러에는 해당 코드 줄을 붙인다."""
    lines = code.splitlines()
    out = [f"[static:{i.code}] {i.message}" for i in errors_of(tb.issues)]
    if comp is not None and not comp.ok:
        for e in comp.primary_errors():
            s = f"[{e.stage}:{e.code or '?'}] {e.message}"
            if e.line:
                s += f" (line {e.line})"
                if 1 <= e.line <= len(lines):
                    s += f"\n      > {lines[e.line - 1].strip()}"
            hint = _HINTS.get(e.code or "")
            if hint:
                s += f"\n      hint: {hint}"
            out.append(s)
    return out[:MAX_PROBLEMS]


def build_repair_prompt(original_prompt: str, code: str, problems: list[str]) -> str:
    """원래 프롬프트 뒤에 직전 코드와 문제 목록을 붙여 '전체 수정본'을 요구한다."""
    numbered = "\n".join(f"{i}. {p}" for i, p in enumerate(problems, 1))
    prev = f"```verilog\n{code.rstrip()}\n```" if code.strip() else "(your previous reply contained no usable module)"
    return (f"{original_prompt}\n\n"
            "## PREVIOUS ATTEMPT (rejected by the automated flow)\n"
            f"{prev}\n\n"
            "## PROBLEMS FOUND\n"
            f"{numbered}\n\n"
            "## TASK\n"
            "Return the COMPLETE corrected testbench (the whole module, not a diff) in one ```verilog block. "
            "Fix every problem above and keep everything unrelated to them unchanged. "
            "All OUTPUT CONTRACT rules still apply.")


# ---------------------------------------------------------------- 루프
def generate_with_gate(summary: dict, sources: dict[str, str], client, compile_fn: Callable[[str, str | None], CompileResult],
                       spec_text: str | None = None, max_attempts: int = 3, model: str | None = None,
                       temperature: float = 0.0, max_output_tokens: int = 8192,
                       on_attempt: Callable[[Attempt], None] | None = None) -> GateRun:
    """TB를 만들고 게이트를 통과할 때까지 최대 max_attempts번 시도한다.

    compile_fn(code, tb_top) -> CompileResult : 보통 compile_check를 rtl_files/work_root와 묶은 함수.
    코드가 없거나 잘린 응답은 컴파일하지 않는다 (잡음 에러만 나오므로). 성공해도 실패해도 모든 시도를 기록한다.
    """
    system, base_prompt = build_tb_prompt(summary, sources, spec_text)
    prompt = base_prompt
    attempts: list[Attempt] = []
    for n in range(1, max_attempts + 1):
        resp = client.generate(LLMRequest(prompt=prompt, system=system, model=model, temperature=temperature,
                                          max_output_tokens=max_output_tokens))
        tb = result_from_response(summary, resp, system, prompt)

        broken = {"no_code", "truncated", "unbalanced_module", "no_module"} & {i.code for i in tb.issues}
        comp = None if (not tb.code or broken) else compile_fn(tb.code, None)
        att = Attempt(n=n, tb=tb, compile=comp)
        if not att.ok:
            att.problems = collect_problems(tb, comp, tb.code)
            if not att.problems:                                     # 방어: 이유 없는 실패는 일반 문구로
                att.problems = ["the testbench was rejected but no specific error was reported"]
        attempts.append(att)
        if on_attempt:
            on_attempt(att)
        if att.ok:
            break
        prompt = build_repair_prompt(base_prompt, tb.code, att.problems)
    return GateRun(attempts=attempts, max_attempts=max_attempts)