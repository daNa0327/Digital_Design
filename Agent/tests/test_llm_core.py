"""LLM 계층 6-1: 요청/응답, 가짜 LLM, 디스크 캐시, LLMClient(캐시, 재시도, 호출 상한)."""

import pytest

from llm import (BudgetExceeded, DailyQuotaExceeded, DiskCache, FakeLLM, LLMClient, LLMError,
                 LLMRequest, LLMResponse, LLMTransientError, RateLimiter, RateLimitError)


class Sleeper:
    """sleep을 기록만 하고 실제로 기다리지 않는다."""

    def __init__(self):
        self.calls = []

    def __call__(self, s):
        self.calls.append(s)


# ------------------------------------------------------------ 요청 / 응답
def test_cache_key_depends_on_every_input_that_changes_the_answer():
    """제공자, 모델, 프롬프트, system, temperature, 출력 상한이 하나라도 다르면 캐시 키가 달라진다."""
    base = LLMRequest(prompt="p")
    k = base.cache_key("gemini", "m1")
    assert k == LLMRequest(prompt="p").cache_key("gemini", "m1")
    assert k != base.cache_key("fake", "m1")
    assert k != base.cache_key("gemini", "m2")
    assert k != LLMRequest(prompt="q").cache_key("gemini", "m1")
    assert k != LLMRequest(prompt="p", system="s").cache_key("gemini", "m1")
    assert k != LLMRequest(prompt="p", temperature=0.7).cache_key("gemini", "m1")
    assert k != LLMRequest(prompt="p", max_output_tokens=10).cache_key("gemini", "m1")


def test_explicit_model_equals_default_model_in_cache_key():
    """요청의 모델을 비워 두는 것과 기본 모델 이름을 직접 쓰는 것은 같은 키다."""
    assert LLMRequest(prompt="p").cache_key("g", "m") == LLMRequest(prompt="p", model="m").cache_key("g", "m")


def test_response_roundtrip_ignores_unknown_keys():
    """응답을 dict로 바꿨다가 되돌려도 같고, 모르는 키가 있어도 읽힌다."""
    r = LLMResponse(text="hi", model="m", input_tokens=3, output_tokens=2, finish_reason="STOP")
    assert LLMResponse.from_dict(r.to_dict()) == r
    assert LLMResponse.from_dict({**r.to_dict(), "future_field": 1}) == r


# ------------------------------------------------------------ FakeLLM
def test_fake_llm_returns_scripted_responses_in_order_and_records_calls():
    """리스트로 준 응답을 순서대로 돌려주고 받은 요청을 calls에 기록한다."""
    f = FakeLLM(["a", "b"])
    assert f.generate(LLMRequest(prompt="1")).text == "a"
    assert f.generate(LLMRequest(prompt="2")).text == "b"
    assert [c.prompt for c in f.calls] == ["1", "2"]


def test_fake_llm_raises_scripted_exceptions_and_runs_out():
    """스크립트에 예외 객체가 있으면 던지고, 응답이 바닥나면 LLMError를 던진다."""
    f = FakeLLM([RateLimitError(), "ok"])
    with pytest.raises(RateLimitError):
        f.generate(LLMRequest(prompt="x"))
    assert f.generate(LLMRequest(prompt="x")).text == "ok"
    with pytest.raises(LLMError):
        f.generate(LLMRequest(prompt="x"))


def test_fake_llm_callable_script():
    """함수로 주면 요청 내용에 따라 응답을 만든다."""
    f = FakeLLM(lambda req: req.prompt.upper())
    assert f.generate(LLMRequest(prompt="abc")).text == "ABC"


# ------------------------------------------------------------ DiskCache
def test_disk_cache_roundtrip_and_overwrite(tmp_path):
    """저장한 값을 같은 키로 읽고, 같은 키에 다시 저장하면 덮어쓰며, 임시 파일이 남지 않는다."""
    c = DiskCache(tmp_path / "cache")
    assert c.get("k") is None
    c.put("k", {"a": 1})
    c.put("k", {"a": 2})
    assert c.get("k") == {"a": 2}
    assert [p.name for p in (tmp_path / "cache").iterdir()] == ["k.json"]


def test_disk_cache_treats_corrupted_file_as_miss(tmp_path):
    """깨진 캐시 파일은 오류 없이 없는 것으로 취급한다."""
    c = DiskCache(tmp_path)
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert c.get("bad") is None


# ------------------------------------------------------------ LLMClient
def test_generate_records_usage():
    """기본 호출: 응답 텍스트를 돌려주고 호출 수와 토큰 사용량을 기록한다."""
    client = LLMClient(FakeLLM(["two words"]))
    r = client.generate(LLMRequest(prompt="one two three"))
    assert r.text == "two words" and r.cached is False
    assert (client.stats.calls, client.stats.input_tokens, client.stats.output_tokens) == (1, 3, 2)


def test_cache_hit_skips_provider_and_is_not_counted_as_a_call(tmp_path):
    """같은 요청을 다시 보내면 제공자를 부르지 않고 cached=True로 돌려주며 호출 수에 세지 않는다."""
    fake = FakeLLM(["x", "y"])
    client = LLMClient(fake, cache=DiskCache(tmp_path))
    first = client.generate(LLMRequest(prompt="p"))
    second = client.generate(LLMRequest(prompt="p"))
    assert (first.text, first.cached, second.text, second.cached) == ("x", False, "x", True)
    assert len(fake.calls) == 1 and client.stats.calls == 1 and client.stats.cache_hits == 1
    assert client.generate(LLMRequest(prompt="other")).text == "y"


def test_cache_persists_across_clients(tmp_path):
    """캐시는 디스크에 있어서 새 클라이언트(다음 실행)에서도 재사용된다."""
    LLMClient(FakeLLM(["x"]), cache=DiskCache(tmp_path)).generate(LLMRequest(prompt="p"))
    fake = FakeLLM([])
    assert LLMClient(fake, cache=DiskCache(tmp_path)).generate(LLMRequest(prompt="p")).text == "x"
    assert fake.calls == []


def test_retry_waits_for_retry_after_when_given():
    """429에 retry_after(초)가 있으면 그만큼 기다렸다가 재시도한다."""
    sleeper = Sleeper()
    client = LLMClient(FakeLLM([RateLimitError("slow", retry_after=7.5), "ok"]), sleep=sleeper)
    assert client.generate(LLMRequest(prompt="p")).text == "ok"
    assert sleeper.calls == [7.5] and client.stats.retries == 1 and client.stats.calls == 2


def test_retry_uses_exponential_backoff_without_retry_after():
    """대기 시간을 모르는 일시 오류는 1, 2, 4초처럼 늘려 가며 재시도한다."""
    sleeper = Sleeper()
    client = LLMClient(FakeLLM([LLMTransientError("a"), LLMTransientError("b"), "ok"]), sleep=sleeper)
    assert client.generate(LLMRequest(prompt="p")).text == "ok"
    assert sleeper.calls == [1.0, 2.0]


def test_backoff_is_capped():
    """대기 시간은 max_backoff를 넘지 않는다."""
    sleeper = Sleeper()
    client = LLMClient(FakeLLM([RateLimitError(retry_after=500), "ok"]), sleep=sleeper, max_backoff=60)
    client.generate(LLMRequest(prompt="p"))
    assert sleeper.calls == [60.0]


def test_retries_are_limited():
    """재시도 횟수를 다 쓰면 마지막 오류를 던지고, 제공자는 max_retries+1번만 불린다."""
    fake = FakeLLM([LLMTransientError("x")] * 10)
    client = LLMClient(fake, max_retries=2, sleep=Sleeper())
    with pytest.raises(LLMTransientError):
        client.generate(LLMRequest(prompt="p"))
    assert len(fake.calls) == 3


def test_non_transient_error_is_not_retried():
    """재시도해도 소용없는 오류(LLMError)는 바로 던진다."""
    fake = FakeLLM([LLMError("bad request"), "ok"])
    client = LLMClient(fake, sleep=Sleeper())
    with pytest.raises(LLMError):
        client.generate(LLMRequest(prompt="p"))
    assert len(fake.calls) == 1


def test_call_budget_stops_run_but_cache_hits_are_free(tmp_path):
    """실행당 호출 상한을 넘으면 BudgetExceeded. 캐시 적중은 상한에 포함되지 않는다."""
    client = LLMClient(FakeLLM(["a", "b", "c"]), cache=DiskCache(tmp_path), max_calls=2)
    client.generate(LLMRequest(prompt="1"))
    client.generate(LLMRequest(prompt="2"))
    assert client.generate(LLMRequest(prompt="1")).cached is True
    with pytest.raises(BudgetExceeded):
        client.generate(LLMRequest(prompt="3"))


def test_budget_also_counts_retries():
    """재시도도 호출로 세므로 상한에 걸리면 재시도 도중에도 멈춘다."""
    client = LLMClient(FakeLLM([RateLimitError(retry_after=0), RateLimitError(retry_after=0), "ok"]),
                       max_calls=2, sleep=Sleeper())
    with pytest.raises(BudgetExceeded):
        client.generate(LLMRequest(prompt="p"))


def test_daily_quota_stops_before_calling_provider(tmp_path):
    """일일 한도에 이미 도달했으면 제공자를 부르지 않고 DailyQuotaExceeded를 던진다."""
    limiter = RateLimiter(rpm=100, rpd=1, state_path=tmp_path / "q.json")
    fake = FakeLLM(["a", "b"])
    client = LLMClient(fake, limiter=limiter)
    client.generate(LLMRequest(prompt="1"))
    with pytest.raises(DailyQuotaExceeded):
        client.generate(LLMRequest(prompt="2"))
    assert len(fake.calls) == 1


def test_every_attempt_including_retries_uses_daily_quota(tmp_path):
    """재시도도 일일 호출 수에 포함한다 (실제 서버에는 요청이 가기 때문)."""
    limiter = RateLimiter(rpm=100, rpd=10, state_path=tmp_path / "q.json")
    client = LLMClient(FakeLLM([RateLimitError(retry_after=0), "ok"]), limiter=limiter, sleep=Sleeper())
    client.generate(LLMRequest(prompt="p"))
    assert limiter.used_today() == 2


def test_cache_hit_does_not_use_daily_quota(tmp_path):
    """캐시 적중은 일일 호출 수를 쓰지 않는다."""
    limiter = RateLimiter(rpm=100, rpd=10, state_path=tmp_path / "q.json")
    client = LLMClient(FakeLLM(["a"]), cache=DiskCache(tmp_path / "c"), limiter=limiter)
    client.generate(LLMRequest(prompt="p"))
    client.generate(LLMRequest(prompt="p"))
    assert limiter.used_today() == 1
