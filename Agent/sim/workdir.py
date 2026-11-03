import re
import uuid
from datetime import datetime
from pathlib import Path

def new_workdir(base: str | Path, label: str = "run") -> Path:
    # 실행마다 고유한 작업 폴더 경로를 만든다 (폴더 생성은 하지 않음).
    label = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(base) / f"{stamp}_{label}_{uuid.uuid4().hex[:4]}"