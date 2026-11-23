"""호출 없이 쓰는 가짜 LLM (테스트와 오프라인 개발용)."""

from __future__ import annotations

from typing import Callable, Union

from llm.base import LLMError, LLMProvider, LLMRequest, LLMResponse

Script = Union[list, Callable[[LLMRequest], "str | Exception"]]


class FakeLLM(LLMProvider):
    """응답을 미리 정해 두고 순서대로(또는 함수로) 돌려준다. 받은 요청을 `calls`에 기록한다.

    responses가 리스트면 호출 순서대로 하나씩 소비한다 (문자열은 응답, 예외 객체는 던짐).
    함수면 요청을 받아 문자열 또는 예외를 돌려준다.
    """

    name = "fake"

    def __init__(self, responses: Script, model: str = "fake-model"):
        self.default_model = model
        self._script = responses
        self._i = 0
        self.calls: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if callable(self._script):
            out = self._script(request)
        else:
            if self._i >= len(self._script):
                raise LLMError("FakeLLM: 준비된 응답이 더 없음")
            out = self._script[self._i]
            self._i += 1
        if isinstance(out, Exception):
            raise out
        return LLMResponse(text=out, model=request.model or self.default_model,
                           input_tokens=len(request.prompt.split()), output_tokens=len(out.split()),
                           finish_reason="STOP")
