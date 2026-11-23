"""LLM 제공자 공통 인터페이스와 오류 계층."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    system: str | None = None
    model: str | None = None            # None이면 제공자의 기본 모델
    temperature: float = 0.0            # 재현성을 위해 기본 0
    max_output_tokens: int | None = None

    def cache_key(self, provider: str, default_model: str) -> str:
        """같은 제공자, 같은 모델, 같은 요청이면 같은 키. 캐시와 재생(replay)에 쓴다."""
        payload = {"provider": provider, "model": self.model or default_model, "prompt": self.prompt,
                   "system": self.system, "temperature": self.temperature,
                   "max_output_tokens": self.max_output_tokens}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False                # 캐시에서 온 응답이면 True (호출 한도를 쓰지 않음)
    latency_s: float = 0.0
    finish_reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LLMResponse":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


class LLMError(Exception):
    """LLM 호출 실패의 기본 오류 (재시도해도 소용없는 종류)."""


class BillingRequired(LLMError):
    """결제나 크레딧이 필요해서 요청이 거절됨 (402). 재시도해도 소용없고 사람이 계정/프로젝트를 확인해야 한다."""


class LLMTransientError(LLMError):
    """잠시 후 재시도하면 성공할 수 있는 오류 (서버 과부하 등)."""


class RateLimitError(LLMTransientError):
    """분당 한도 초과 등 (429). retry_after(초)를 알면 담는다."""

    def __init__(self, message: str = "rate limited", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class DailyQuotaExceeded(LLMError):
    """일일 한도 소진. 재시도해도 소용없고 한도가 초기화될 때까지 기다려야 한다."""


class BudgetExceeded(LLMError):
    """한 번의 실행에서 허용한 호출 횟수(상한)를 넘었다 (우리 쪽 안전장치)."""


class LLMProvider(ABC):
    name: str = "base"
    default_model: str = ""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """요청 하나를 보내고 응답을 돌려준다. 실패는 LLMError 계열로 던진다."""