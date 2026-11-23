"""LLM 계층 6-1: .env 로더, 설정, Gemini 제공자(가짜 SDK 클라이언트로 오류 변환과 요청 형식 검증)."""

import pytest

from llm import (BillingRequired, DailyQuotaExceeded, LLMClient, LLMError, LLMRequest, LLMTransientError,
                 RateLimitError)
from llm.config import ConfigError, LLMConfig, load_env, make_client
from llm.gemini import GeminiProvider


# ------------------------------------------------------------ .env 로더
def test_load_env_parses_common_forms(tmp_path, monkeypatch):
    """`KEY=V`, 공백 있는 `KEY = V`, 따옴표, 주석, export 접두사, 빈 줄을 모두 읽는다."""
    for k in ("A", "B", "C", "D", "E"):
        monkeypatch.delenv(k, raising=False)
    p = tmp_path / ".env"
    p.write_text('# comment\n\nA=1\nB = 2\nC="three words"\nexport D=4\nE=5 # trailing\nnot a pair\n',
                 encoding="utf-8")
    assert load_env(p) == {"A": "1", "B": "2", "C": "three words", "D": "4", "E": "5"}


def test_load_env_does_not_override_existing_and_handles_bom(tmp_path, monkeypatch):
    """이미 설정된 환경 변수는 덮어쓰지 않고, 윈도우 메모장의 BOM이 있어도 첫 줄을 읽는다."""
    monkeypatch.setenv("KEEP", "shell")
    monkeypatch.delenv("FIRST", raising=False)
    p = tmp_path / ".env"
    p.write_bytes("﻿FIRST=1\nKEEP=file\n".encode("utf-8"))
    load_env(p)
    import os
    assert os.environ["FIRST"] == "1" and os.environ["KEEP"] == "shell"


def test_load_env_missing_file_is_empty(tmp_path):
    """.env가 없으면 빈 결과 (오류 아님)."""
    assert load_env(tmp_path / "nope.env") == {}


# ------------------------------------------------------------ 설정
def test_config_defaults_and_overrides(monkeypatch):
    """기본값(Gemini, 분당 12, 일일 450)과 환경 변수 재정의, none은 제한 없음."""
    for k in ("RVA_LLM_PROVIDER", "RVA_LLM_MODEL", "RVA_LLM_RPM", "RVA_LLM_RPD", "RVA_LLM_MAX_CALLS"):
        monkeypatch.delenv(k, raising=False)
    c = LLMConfig.from_env()
    assert (c.provider, c.model, c.rpm, c.rpd, c.max_calls_per_run) == ("gemini", "", 12, 450, None)
    monkeypatch.setenv("RVA_LLM_MODEL", "m")
    monkeypatch.setenv("RVA_LLM_RPM", "5")
    monkeypatch.setenv("RVA_LLM_RPD", "none")
    monkeypatch.setenv("RVA_LLM_MAX_CALLS", "30")
    c = LLMConfig.from_env()
    assert (c.model, c.rpm, c.rpd, c.max_calls_per_run) == ("m", 5, None, 30)


def test_config_rejects_non_integer(monkeypatch):
    """숫자 설정에 숫자가 아닌 값이 있으면 어떤 항목인지 알려 주는 ConfigError."""
    monkeypatch.setenv("RVA_LLM_RPM", "fast")
    with pytest.raises(ConfigError, match="RVA_LLM_RPM"):
        LLMConfig.from_env()


def test_make_client_requires_model_and_key(monkeypatch, tmp_path):
    """모델이 없으면 list-models 안내와 함께, 키가 없으면 키 설정 안내와 함께 ConfigError."""
    monkeypatch.setattr("llm.config.load_env", lambda *a, **k: {})
    monkeypatch.delenv("RVA_LLM_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="list-models"):
        make_client(LLMConfig(model=""))
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        make_client(LLMConfig(model="m", cache_dir=tmp_path, quota_path=tmp_path / "q.json"))


def test_make_client_rejects_unknown_provider(monkeypatch, tmp_path):
    """지원하지 않는 제공자 이름이면 ConfigError."""
    monkeypatch.setattr("llm.config.load_env", lambda *a, **k: {})
    with pytest.raises(ConfigError, match="제공자"):
        make_client(LLMConfig(provider="nope", model="m", cache_dir=tmp_path, quota_path=tmp_path / "q.json"))


def test_make_client_builds_gemini_client_without_network(monkeypatch, tmp_path):
    """키와 모델이 있으면 네트워크 호출 없이 Gemini 클라이언트(캐시, 한도 제어 포함)를 만든다."""
    pytest.importorskip("google.genai")
    monkeypatch.setattr("llm.config.load_env", lambda *a, **k: {})
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-test")
    client = make_client(LLMConfig(model="m", rpm=5, rpd=7, cache_dir=tmp_path / "c", quota_path=tmp_path / "q.json"))
    assert client.provider.name == "gemini" and client.provider.default_model == "m"
    assert client.limiter.rpm == 5 and client.limiter.rpd == 7 and client.cache is not None


# ------------------------------------------------------------ Gemini 제공자
class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeSDK:
    """google-genai 클라이언트 흉내: models.generate_content / models.list."""

    def __init__(self, result=None, error=None, models=None):
        self.result, self.error, self.calls = result, error, []
        self._models = models or []
        self.models = _Obj(generate_content=self._gen, list=lambda: iter(self._models))

    def _gen(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.result


def ok_result(text="hello", prompt_tokens=11, out_tokens=3, finish="STOP"):
    return _Obj(text=text, usage_metadata=_Obj(prompt_token_count=prompt_tokens, candidates_token_count=out_tokens),
                candidates=[_Obj(finish_reason=_Obj(name=finish))])


class FakeAPIError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def test_gemini_sends_model_prompt_and_only_the_config_that_was_set():
    """모델, 프롬프트, temperature는 항상, system과 출력 상한은 지정했을 때만 config에 넣는다."""
    sdk = FakeSDK(ok_result())
    p = GeminiProvider(model="m1", client=sdk)
    p.generate(LLMRequest(prompt="hi"))
    assert sdk.calls[0] == {"model": "m1", "contents": "hi", "config": {"temperature": 0.0}}
    p.generate(LLMRequest(prompt="hi", system="be brief", max_output_tokens=50, model="m2", temperature=0.3))
    assert sdk.calls[1] == {"model": "m2", "contents": "hi",
                            "config": {"temperature": 0.3, "system_instruction": "be brief", "max_output_tokens": 50}}


def test_gemini_parses_text_tokens_and_finish_reason():
    """응답 텍스트, 입력/출력 토큰 수, 종료 사유를 읽는다."""
    r = GeminiProvider(model="m", client=FakeSDK(ok_result("abc", 7, 2, "MAX_TOKENS"))).generate(LLMRequest(prompt="x"))
    assert (r.text, r.model, r.input_tokens, r.output_tokens, r.finish_reason) == ("abc", "m", 7, 2, "MAX_TOKENS")


def test_gemini_tolerates_missing_usage_and_empty_text():
    """사용량 정보나 텍스트가 없는 응답도 오류 없이 0과 빈 문자열로 처리한다."""
    r = GeminiProvider(model="m", client=FakeSDK(_Obj(text=None))).generate(LLMRequest(prompt="x"))
    assert (r.text, r.input_tokens, r.output_tokens, r.finish_reason) == ("", 0, 0, None)


def test_gemini_requires_model_and_key():
    """모델을 지정하지 않았거나 키가 없으면 호출 전에 LLMError."""
    with pytest.raises(LLMError, match="모델"):
        GeminiProvider(client=FakeSDK(ok_result())).generate(LLMRequest(prompt="x"))
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiProvider(api_key="", model="m")


@pytest.mark.parametrize("code,msg,cls,retry_after", [
    (429, "Quota exceeded. Please retry in 7.5s.", RateLimitError, 7.5),
    (429, "Quota exceeded for metric requests per day", DailyQuotaExceeded, None),
    (429, "limit: GenerateRequestsPerDayPerProjectPerModel", DailyQuotaExceeded, None),
    (503, "model overloaded", LLMTransientError, None),
    (500, "internal", LLMTransientError, None),
])
def test_gemini_maps_errors_to_retry_policy(code, msg, cls, retry_after):
    """429(분당)은 대기 시간과 함께 재시도 대상, 429(일일)는 중단, 5xx는 일시 오류로 변환한다."""
    with pytest.raises(cls) as ei:
        GeminiProvider(model="m", client=FakeSDK(error=FakeAPIError(code, msg))).generate(LLMRequest(prompt="x"))
    assert type(ei.value) is cls
    assert getattr(ei.value, "retry_after", None) == retry_after


def test_gemini_402_is_a_billing_error_with_guidance_and_is_not_retried():
    """402(프리페이 크레딧 소진 등)는 BillingRequired로 변환하고 Projects 페이지 확인을 안내하며 재시도하지 않는다."""
    err = FakeAPIError(402, "Your prepayment credits are depleted.")
    sdk = FakeSDK(error=err)
    client = LLMClient(GeminiProvider(model="m", client=sdk), sleep=lambda s: None)
    with pytest.raises(BillingRequired, match="Projects"):
        client.generate(LLMRequest(prompt="x"))
    assert len(sdk.calls) == 1 and not issubclass(BillingRequired, LLMTransientError)


def test_gemini_other_errors_are_not_retryable():
    """잘못된 요청(400)이나 코드가 없는 예외는 재시도 대상이 아닌 LLMError다."""
    for err in (FakeAPIError(400, "bad request"), ValueError("boom")):
        with pytest.raises(LLMError) as ei:
            GeminiProvider(model="m", client=FakeSDK(error=err)).generate(LLMRequest(prompt="x"))
        assert not isinstance(ei.value, LLMTransientError) and not isinstance(ei.value, DailyQuotaExceeded)


def test_gemini_maps_real_sdk_error_objects():
    """실제 google-genai의 오류 객체(429, 503)도 같은 규칙으로 변환된다."""
    errors = pytest.importorskip("google.genai.errors")
    e429 = errors.APIError(429, {"error": {"message": "Please retry in 3s.", "status": "RESOURCE_EXHAUSTED"}})
    with pytest.raises(RateLimitError) as ei:
        GeminiProvider(model="m", client=FakeSDK(error=e429)).generate(LLMRequest(prompt="x"))
    assert ei.value.retry_after == 3.0
    e503 = errors.ServerError(503, {"error": {"message": "overloaded", "status": "UNAVAILABLE"}})
    with pytest.raises(LLMTransientError):
        GeminiProvider(model="m", client=FakeSDK(error=e503)).generate(LLMRequest(prompt="x"))


def test_gemini_list_models_strips_prefix_and_sorts():
    """모델 목록은 `models/` 접두사를 떼고 정렬해서 돌려준다."""
    sdk = FakeSDK(models=[_Obj(name="models/b-model"), _Obj(name="models/a-model")])
    assert GeminiProvider(model="m", client=sdk).list_models() == ["a-model", "b-model"]


def test_client_retries_gemini_rate_limit_end_to_end():
    """LLMClient 위에서 429(대기 시간 포함)를 만나면 기다렸다가 재시도해 성공한다."""
    class Flaky(FakeSDK):
        def _gen(self, **kw):
            self.calls.append(kw)
            if len(self.calls) == 1:
                raise FakeAPIError(429, "Please retry in 2s.")
            return self.result

    slept = []
    sdk = Flaky(ok_result("done"))
    client = LLMClient(GeminiProvider(model="m", client=sdk), sleep=slept.append)
    assert client.generate(LLMRequest(prompt="x")).text == "done"
    assert slept == [2.0] and len(sdk.calls) == 2