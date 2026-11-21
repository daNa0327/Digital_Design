"""버그 주입 카탈로그와 패치 적용.

설계
- 카탈로그(bugs.json)가 단일 원본이다. 변형 RTL을 따로 저장하지 않고 필요할 때 골든 RTL에 패치를 적용해 만든다.
- 패치는 "한 줄 문자열 치환"이다. find가 정확히 expect_count번 나타나지 않으면 오류로 멈춘다
  (골든 RTL이 바뀌었는데 메타데이터가 낡은 채로 평가되는 일을 막는다).
- 줄바꿈은 읽을 때 \\n으로 통일하므로 Windows(CRLF) 파일에도 동일하게 적용된다.
- 정답 메타데이터(파일, 줄, 유형, 동등 변형 여부)는 평가의 정답지다. Agent에게는 보여주지 않는다.
"""

from __future__ import annotations

import difflib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

BUG_TYPES = ("pointer", "flag", "reset", "memory", "guard", "corner")


class BugPatchError(Exception):
    """패치를 골든 RTL에 적용할 수 없음 (find 불일치 등)."""


@dataclass(frozen=True)
class Bug:
    id: str
    dut: str
    type: str
    file: str
    find: str
    replace: str
    expect_count: int
    occurrence: int
    description: str
    equivalent: bool


@dataclass(frozen=True)
class AppliedBug:
    bug: Bug
    rtl_dir: Path        # 변형 RTL이 들어 있는 폴더 (골든과 같은 파일 구성)
    line: int            # 골든 파일에서 바뀐 줄 번호 (1부터)
    diff: str            # unified diff


_REQUIRED = ("id", "dut", "type", "file", "find", "replace", "expect_count",
             "description", "equivalent")


def load_catalog(path: str | Path) -> list[Bug]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    bugs: list[Bug] = []
    seen: set[str] = set()
    for i, d in enumerate(data["bugs"]):
        missing = [k for k in _REQUIRED if k not in d]
        if missing:
            raise ValueError(f"bugs[{i}]에 필수 키가 없습니다: {missing}")
        if d["type"] not in BUG_TYPES:
            raise ValueError(f"{d['id']}: 알 수 없는 type {d['type']!r} (허용: {BUG_TYPES})")
        if d["id"] in seen:
            raise ValueError(f"id가 중복되었습니다: {d['id']}")
        occ = d.get("occurrence", 1)
        if not (1 <= occ <= d["expect_count"]):
            raise ValueError(f"{d['id']}: occurrence는 1..expect_count 범위여야 합니다")
        seen.add(d["id"])
        bugs.append(Bug(d["id"], d["dut"], d["type"], d["file"], d["find"], d["replace"],
                        d["expect_count"], occ, d["description"], bool(d["equivalent"])))
    return bugs


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")      # 줄바꿈은 \n으로 통일됨


def apply_bug(bug: Bug, golden_rtl_dir: str | Path, out_dir: str | Path) -> AppliedBug:
    """골든 RTL 폴더를 out_dir로 복사하고 bug.file에만 패치를 적용한다."""
    golden = Path(golden_rtl_dir)
    out = Path(out_dir)
    if out.exists():
        raise FileExistsError(f"출력 폴더가 이미 있습니다: {out}")

    src_file = golden / bug.file
    if not src_file.is_file():
        raise BugPatchError(f"{bug.id}: 골든에 {bug.file}이 없습니다")
    text = _read(src_file)

    n = text.count(bug.find)
    if n == 0 or n != bug.expect_count:
        raise BugPatchError(f"{bug.id}: {bug.file}에서 {bug.find!r}가 {n}번 나타납니다 "
                            f"(기대 {bug.expect_count}번). 골든 RTL이 바뀌었는지 확인하세요")

    idx = -1
    for _ in range(bug.occurrence):                  # occurrence번째 일치 위치
        idx = text.index(bug.find, idx + 1)
    line = text.count("\n", 0, idx) + 1
    mutated = text[:idx] + bug.replace + text[idx + len(bug.find):]
    if mutated == text:
        raise BugPatchError(f"{bug.id}: 치환 결과가 원본과 같습니다")

    shutil.copytree(golden, out)
    (out / bug.file).write_text(mutated, encoding="utf-8", newline="\n")

    diff = "".join(difflib.unified_diff(
        text.splitlines(keepends=True), mutated.splitlines(keepends=True),
        fromfile=f"golden/{bug.file}", tofile=f"{bug.id}/{bug.file}"))
    return AppliedBug(bug, out, line, diff)