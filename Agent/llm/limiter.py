"""호출 한도 제어: 분당 요청 수(RPM)는 기다리고, 일일 요청 수(RPD)는 디스크에 세어 초과 시 중단한다."""

from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from llm.base import DailyQuotaExceeded


def _pacific_tz():
    """RPD는 태평양 시간 자정에 초기화된다. IANA 데이터가 없는 환경(Windows 등)이면 UTC-8로 대체."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/Los_Angeles")
    except Exception:                                  # tzdata 미설치 등
        return timezone(timedelta(hours=-8))


class RateLimiter:
    def __init__(self, rpm: int, rpd: int | None = None, state_path: str | Path | None = None,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 tz=None):
        if rpm <= 0:
            raise ValueError("rpm은 1 이상이어야 함")
        self.rpm, self.rpd = rpm, rpd
        self.state_path = Path(state_path) if state_path else None
        self._clock, self._sleep = clock, sleep
        self._tz = tz or _pacific_tz()
        self._window: deque[float] = deque()

    # ---- 일일 카운터 (디스크에 유지: 프로그램을 다시 실행해도 이어짐)
    def _day_key(self, now: float) -> str:
        return datetime.fromtimestamp(now, self._tz).strftime("%Y-%m-%d")

    def _load(self, now: float) -> dict:
        day = self._day_key(now)
        if self.state_path:
            try:
                st = json.loads(self.state_path.read_text(encoding="utf-8"))
                if st.get("day") == day:
                    return {"day": day, "count": int(st.get("count", 0))}
            except (OSError, ValueError):
                pass
        return {"day": day, "count": 0}

    def _save(self, st: dict) -> None:
        if self.state_path:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(st), encoding="utf-8")

    def used_today(self) -> int:
        return self._load(self._clock())["count"]

    def remaining_today(self) -> int | None:
        return None if self.rpd is None else max(0, self.rpd - self.used_today())

    def acquire(self) -> None:
        """호출 직전에 부른다. 분당 한도면 필요한 만큼 기다리고, 일일 한도를 넘으면 예외."""
        now = self._clock()
        st = self._load(now)
        if self.rpd is not None and st["count"] >= self.rpd:
            raise DailyQuotaExceeded(f"일일 호출 상한({self.rpd}회)에 도달함 - 태평양 시간 자정(한국 시간 오후 4~5시)에 초기화")
        while self._window and now - self._window[0] >= 60:
            self._window.popleft()
        if len(self._window) >= self.rpm:
            self._sleep(60 - (now - self._window[0]) + 0.01)
            now = self._clock()
            while self._window and now - self._window[0] >= 60:
                self._window.popleft()
        self._window.append(now)
        st["count"] += 1
        self._save(st)
