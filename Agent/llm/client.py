"""LLMClient: 제공자 위에 캐시, 한도 제어, 재시도, 호출 상한, 사용량 기록을 얹는다."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from llm.base import (BudgetExceeded, LLMProvider, LLMRequest, LLMResponse, LLMTransientError,
                      RateLimitError)
from llm.cache import DiskCache
from llm.limiter import RateLimiter


@dataclass
class UsageStats:
    calls: int = 0           # 제공자를 실제로 부른 횟수 (재시도 포함)
    cache_hits: int = 0
    retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def is_cacheable(resp: LLMResponse) -> bool:
    """캐시에 저장하고 재사용해도 되는 응답인가.

    빈 응답이나 STOP이 아닌 이유(MALFORMED_FUNCTION_CALL, MAX_TOKENS 등)로 끝난 응답은 일시적 실패일 수 있다.
    저장하면 같은 요청을 다시 보내도 그 실패가 그대로 재생되어 재시도가 소용없어지고, 이어하기(--resume)에서도 반복된다.
    """
    return bool(resp.text and resp.text.strip()) and resp.finish_reason in (None, "STOP")


class LLMClient:
    def __init__(self, provider: LLMProvider, cache: DiskCache | None = None,
                 limiter: RateLimiter | None = None, max_retries: int = 3, backoff_base: float = 2.0,
                 max_backoff: float = 60.0, max_calls: int | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.provider, self.cache, self.limiter = provider, cache, limiter
        self.max_retries, self.backoff_base, self.max_backoff = max_retries, backoff_base, max_backoff
        self.max_calls = max_calls
        self._sleep = sleep
        self.stats = UsageStats()

    def generate(self, request: LLMRequest) -> LLMResponse:
        key = request.cache_key(self.provider.name, self.provider.default_model)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                cached_resp = LLMResponse.from_dict(hit)
                # 이전 버전이 저장해 둔 빈 응답이나 잘린 응답은 없는 것으로 친다 (다시 호출해서 덮어쓴다)
                if is_cacheable(cached_resp):
                    self.stats.cache_hits += 1
                    cached_resp.cached = True
                    return cached_resp

        for attempt in range(self.max_retries + 1):
            if self.max_calls is not None and self.stats.calls >= self.max_calls:
                raise BudgetExceeded(f"이번 실행의 호출 상한({self.max_calls}회)을 넘음")
            if self.limiter is not None:
                self.limiter.acquire()                   # 일일 한도 초과면 여기서 예외 (재시도 안 함)
            self.stats.calls += 1
            started = time.monotonic()
            try:
                resp = self.provider.generate(request)
            except LLMTransientError as e:
                if attempt == self.max_retries:
                    raise
                self.stats.retries += 1
                wait = getattr(e, "retry_after", None)
                if wait is None:
                    wait = self.backoff_base ** attempt
                self._sleep(min(float(wait), self.max_backoff))
                continue
            resp.latency_s = resp.latency_s or (time.monotonic() - started)
            self.stats.input_tokens += resp.input_tokens
            self.stats.output_tokens += resp.output_tokens
            if self.cache is not None and is_cacheable(resp):
                self.cache.put(key, resp.to_dict())
            return resp
        raise RateLimitError("재시도 횟수를 모두 사용함")   # 도달하지 않음 (루프 안에서 raise)
