"""설정 로드: .env 파일과 환경 변수에서 읽는다. 키 값은 로그나 예외 메시지에 넣지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from llm.base import LLMError, LLMProvider
from llm.cache import DiskCache
from llm.client import LLMClient
from llm.limiter import RateLimiter

ROOT = Path(__file__).resolve().parents[1]


class ConfigError(LLMError):
    pass


def load_env(path: str | Path | None = None) -> dict[str, str]:
    """`KEY=VALUE` 형식의 .env를 읽어 환경 변수에 넣는다 (이미 있는 값은 덮어쓰지 않음).

    공백(`KEY = VALUE`), 따옴표, `#` 주석, `export ` 접두사를 허용한다. 읽은 항목을 돌려준다.
    """
    p = Path(path) if path else ROOT / ".env"
    found: dict[str, str] = {}
    try:
        lines = p.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return found
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            found[key] = value
            os.environ.setdefault(key, value)
    return found


@dataclass
class LLMConfig:
    provider: str = "gemini"
    model: str = ""                    # 필수 (list-models로 확인한 이름)
    rpm: int = 12                      # 무료 한도(예: 15)보다 여유를 둔 값
    rpd: int | None = 450              # 무료 한도(예: 500)보다 여유를 둔 값
    max_calls_per_run: int | None = None
    cache_dir: Path = ROOT / "runs" / "llm" / "cache"
    quota_path: Path = ROOT / "runs" / "llm" / "quota.json"

    @classmethod
    def from_env(cls) -> "LLMConfig":
        def num(name: str, default):
            v = os.environ.get(name)
            if v is None or v == "":
                return default
            if v.lower() in ("none", "off", "unlimited"):
                return None
            try:
                return int(v)
            except ValueError as e:
                raise ConfigError(f"{name}은(는) 정수여야 함: {v!r}") from e

        return cls(provider=os.environ.get("RVA_LLM_PROVIDER", "gemini").strip().lower(),
                   model=os.environ.get("RVA_LLM_MODEL", "").strip(),
                   rpm=num("RVA_LLM_RPM", 12), rpd=num("RVA_LLM_RPD", 450),
                   max_calls_per_run=num("RVA_LLM_MAX_CALLS", None))


def make_provider(cfg: LLMConfig) -> LLMProvider:
    if cfg.provider == "gemini":
        from llm.gemini import GeminiProvider
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ConfigError("GEMINI_API_KEY가 없음 (.env 또는 환경 변수에 설정)")
        return GeminiProvider(api_key=key, model=cfg.model)
    raise ConfigError(f"지원하지 않는 제공자: {cfg.provider!r}")


def make_client(cfg: LLMConfig | None = None, use_cache: bool = True) -> LLMClient:
    """설정으로 LLMClient를 만든다 (제공자 + 캐시 + 한도 제어 + 호출 상한)."""
    load_env()
    cfg = cfg or LLMConfig.from_env()
    if not cfg.model:
        raise ConfigError("RVA_LLM_MODEL이 없음 - `python -m scripts.llm_ping --list-models`로 이름을 확인해 .env에 설정")
    provider = make_provider(cfg)
    return LLMClient(provider,
                     cache=DiskCache(cfg.cache_dir) if use_cache else None,
                     limiter=RateLimiter(cfg.rpm, cfg.rpd, state_path=cfg.quota_path),
                     max_calls=cfg.max_calls_per_run)
