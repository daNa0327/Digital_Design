"""디스크 캐시: 같은 요청이면 이전 응답을 재사용해 호출을 아낀다."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class DiskCache:
    """키 하나당 JSON 파일 하나. 깨진 파일은 없는 것으로 취급한다."""

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> dict | None:
        try:
            return json.loads(self._path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, key: str, value: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False)
            os.replace(tmp, self._path(key))      # 쓰는 도중 중단돼도 반쪽짜리 파일이 남지 않음
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
