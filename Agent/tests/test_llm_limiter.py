"""LLM 계층 6-1: 호출 한도 제어(분당 대기, 일일 카운터의 디스크 유지와 날짜 경계)."""

from datetime import datetime, timezone

import pytest

from llm import DailyQuotaExceeded, RateLimiter
from llm.limiter import _pacific_tz


class FakeTime:
    """sleep하면 시계가 그만큼 흐르는 가짜 시간."""

    def __init__(self, start=1_000_000.0):
        self.t = start
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def make(rpm=2, rpd=None, path=None, ft=None, tz=timezone.utc):
    ft = ft or FakeTime()
    return RateLimiter(rpm, rpd, state_path=path, clock=ft.now, sleep=ft.sleep, tz=tz), ft


def test_rpm_allows_burst_then_waits_until_window_frees():
    """분당 2회 한도: 처음 2번은 바로, 3번째는 첫 호출로부터 60초가 지날 때까지 기다린다."""
    lim, ft = make(rpm=2)
    lim.acquire(); lim.acquire()
    assert ft.slept == []
    lim.acquire()
    assert len(ft.slept) == 1 and 59.9 < ft.slept[0] < 60.1


def test_rpm_does_not_wait_after_window_has_passed():
    """60초가 지난 뒤의 호출은 기다리지 않는다."""
    lim, ft = make(rpm=1)
    lim.acquire()
    ft.t += 61
    lim.acquire()
    assert ft.slept == []


def test_rpm_wait_is_only_the_remaining_time():
    """일부 시간이 이미 흘렀으면 남은 시간만 기다린다."""
    lim, ft = make(rpm=1)
    lim.acquire()
    ft.t += 45
    lim.acquire()
    assert 14.9 < ft.slept[0] < 15.2


def test_rpd_blocks_at_limit_and_reports_remaining(tmp_path):
    """일일 3회 한도: 3번 후 4번째는 DailyQuotaExceeded, 남은 횟수는 0."""
    lim, _ = make(rpm=100, rpd=3, path=tmp_path / "q.json")
    for _ in range(3):
        lim.acquire()
    assert lim.remaining_today() == 0
    with pytest.raises(DailyQuotaExceeded):
        lim.acquire()


def test_rpd_counter_survives_restart(tmp_path):
    """일일 카운터는 디스크에 있어서 프로그램을 다시 실행해도(새 RateLimiter) 이어진다."""
    path = tmp_path / "q.json"
    ft = FakeTime()
    a, _ = make(rpm=100, rpd=2, path=path, ft=ft)
    a.acquire(); a.acquire()
    b, _ = make(rpm=100, rpd=2, path=path, ft=ft)
    assert b.used_today() == 2
    with pytest.raises(DailyQuotaExceeded):
        b.acquire()


def test_rpd_resets_at_midnight_of_configured_timezone(tmp_path):
    """날짜가 바뀌면(설정한 시간대의 자정) 일일 카운터가 0으로 돌아간다."""
    path = tmp_path / "q.json"
    start = datetime(2026, 11, 23, 23, 59, 0, tzinfo=timezone.utc).timestamp()
    lim, ft = make(rpm=100, rpd=2, path=path, ft=FakeTime(start))
    lim.acquire(); lim.acquire()
    with pytest.raises(DailyQuotaExceeded):
        lim.acquire()
    ft.t += 120                                       # 자정을 넘김
    assert lim.used_today() == 0
    lim.acquire()
    assert lim.used_today() == 1


def test_no_daily_limit_means_unlimited_and_remaining_is_none():
    """rpd를 주지 않으면 일일 제한이 없고 remaining_today는 None이다."""
    lim, _ = make(rpm=100, rpd=None)
    for _ in range(50):
        lim.acquire()
    assert lim.remaining_today() is None


def test_corrupted_state_file_resets_counter(tmp_path):
    """상태 파일이 깨져 있어도 오류 없이 0에서 다시 시작한다."""
    path = tmp_path / "q.json"
    path.write_text("garbage", encoding="utf-8")
    lim, _ = make(rpm=100, rpd=2, path=path)
    assert lim.used_today() == 0


def test_invalid_rpm_is_rejected():
    """rpm이 0 이하이면 만들 때 바로 오류."""
    with pytest.raises(ValueError):
        RateLimiter(0)


def test_pacific_timezone_is_always_available():
    """IANA 데이터가 없는 환경이어도 시간대 객체를 만들어 날짜 계산이 된다."""
    assert datetime.fromtimestamp(0, _pacific_tz()).year in (1969, 1970)
