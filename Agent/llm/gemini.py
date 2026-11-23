"""Gemini 제공자 (google-genai SDK). 무료 티어 키로 동작한다.

SDK는 호출 시점에 가져온다 (설치하지 않아도 다른 모듈은 쓸 수 있음).
테스트에서는 `client=`로 가짜 SDK 클라이언트를 주입한다.
"""

from __future__ import annotations

import re
import time

from llm.base import (BillingRequired, DailyQuotaExceeded, LLMError, LLMProvider, LLMRequest, LLMResponse,
                      LLMTransientError, RateLimitError)

_RETRY_IN = re.compile(r"retry in (\d+(?:\.\d+)?)\s*s", re.I)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str = "", client=None):
        self.default_model = model
        if client is None:
            if not api_key:
                raise LLMError("GEMINI_API_KEY가 설정되지 않음")
            from google import genai
            client = genai.Client(api_key=api_key)
        self._client = client

    # ---- 호출
    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.default_model
        if not model:
            raise LLMError("모델이 지정되지 않음 (RVA_LLM_MODEL 설정 필요)")
        config: dict = {"temperature": request.temperature}
        if request.system:
            config["system_instruction"] = request.system
        if request.max_output_tokens:
            config["max_output_tokens"] = request.max_output_tokens
        started = time.monotonic()
        try:
            resp = self._client.models.generate_content(model=model, contents=request.prompt, config=config)
        except LLMError:
            raise
        except Exception as e:                         # SDK 오류를 우리 오류 계층으로 변환
            raise self._map_error(e) from e
        um = getattr(resp, "usage_metadata", None)
        finish = None
        cands = getattr(resp, "candidates", None) or []
        if cands:
            fr = getattr(cands[0], "finish_reason", None)
            finish = getattr(fr, "name", None) or (str(fr) if fr is not None else None)
        return LLMResponse(text=getattr(resp, "text", None) or "", model=model,
                           input_tokens=getattr(um, "prompt_token_count", 0) or 0,
                           output_tokens=getattr(um, "candidates_token_count", 0) or 0,
                           latency_s=time.monotonic() - started, finish_reason=finish)

    @staticmethod
    def _map_error(e: Exception) -> LLMError:
        code = getattr(e, "code", None)
        msg = str(getattr(e, "message", None) or e)
        if code == 402:
            return BillingRequired(
                "결제/크레딧 문제(402): 이 프로젝트가 프리페이 크레딧이 없는 상태이거나 무료 티어를 쓸 수 없는 상태. "
                f"AI Studio의 Projects 페이지에서 프로젝트의 Billing Tier와 상태를 확인하세요. 원문: {msg[:150]}")
        if code == 429:
            if re.search(r"per\s*day|PerDay", msg, re.I):
                return DailyQuotaExceeded(f"일일 한도 소진: {msg[:200]}")
            m = _RETRY_IN.search(msg)
            return RateLimitError(msg[:200], retry_after=float(m.group(1)) if m else None)
        if isinstance(code, int) and 500 <= code < 600:
            return LLMTransientError(f"서버 오류 {code}: {msg[:200]}")
        return LLMError(f"Gemini 호출 실패 (code={code}): {msg[:300]}")

    # ---- 보조
    def list_models(self) -> list[str]:
        """이 키로 볼 수 있는 모델 이름 목록 (`models/` 접두사 제거)."""
        return sorted(str(getattr(m, "name", m)).removeprefix("models/") for m in self._client.models.list())