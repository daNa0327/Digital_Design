"""버그 카탈로그와 패치 적용 테스트 (Vivado 불필요).

평가의 정답지가 되는 메타데이터가 골든 RTL과 항상 일치하는지를 검증한다.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.bugs import BUG_TYPES, BugPatchError, apply_bug, load_catalog

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "bugs" / "sync_fifo" / "bugs.json"
GOLDEN = ROOT / "dut" / "sync_fifo" / "rtl"


@pytest.fixture(scope="module")
def bugs():
    return load_catalog(CATALOG)


def test_catalog_has_unique_ids_and_covers_all_types(bugs):
    """id가 유일하고 모든 유형(pointer/flag/reset/memory/guard/corner)이 하나 이상 있다."""
    ids = [b.id for b in bugs]
    assert len(ids) == len(set(ids)) and len(bugs) >= 15
    assert {b.type for b in bugs} == set(BUG_TYPES)


def test_equivalent_mutants_are_exactly_the_dead_branch_ones(bugs):
    """동등 변형(top 기준 관측 불가)은 도달 불가 분기를 바꾼 두 개뿐이다."""
    assert {b.id for b in bugs if b.equivalent} == {"E01_dead_full_branch", "E02_dead_empty_branch"}


def test_every_bug_applies_and_changes_exactly_one_line(bugs, tmp_path):
    """모든 패치가 골든에 깔끔하게 적용되고 diff가 정확히 한 줄 교체(-1줄 +1줄)다."""
    for b in bugs:
        a = apply_bug(b, GOLDEN, tmp_path / b.id)
        body = [l for l in a.diff.splitlines()
                if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        assert [l[0] for l in body] == ["-", "+"], b.id


def test_reported_line_points_at_the_patched_text(bugs, tmp_path):
    """메타데이터의 줄 번호가 골든 파일에서 실제로 find 텍스트가 있는 줄이다."""
    for b in bugs:
        a = apply_bug(b, GOLDEN, tmp_path / b.id)
        golden_line = (GOLDEN / b.file).read_text(encoding="utf-8", errors="replace").splitlines()[a.line - 1]
        assert b.find in golden_line, b.id


def test_apply_leaves_golden_and_other_files_untouched(bugs, tmp_path):
    """골든은 그대로이고, 패치 대상이 아닌 파일은 변형 폴더에서도 바이트까지 같다."""
    before = {p.name: p.read_bytes() for p in GOLDEN.glob("*.v")}
    b = bugs[0]
    a = apply_bug(b, GOLDEN, tmp_path / "m")
    assert {p.name: p.read_bytes() for p in GOLDEN.glob("*.v")} == before
    for p in a.rtl_dir.glob("*.v"):
        if p.name != b.file:
            assert p.read_bytes() == before[p.name]
        else:
            assert p.read_bytes() != before[p.name]


def test_patch_mismatch_and_existing_outdir_raise(bugs, tmp_path):
    """find 횟수가 기대와 다르면 BugPatchError, 출력 폴더가 있으면 FileExistsError."""
    with pytest.raises(BugPatchError):
        apply_bug(replace(bugs[0], expect_count=bugs[0].expect_count + 1), GOLDEN, tmp_path / "x")
    with pytest.raises(BugPatchError):
        apply_bug(replace(bugs[0], find="not_in_file_zzz", expect_count=0), GOLDEN, tmp_path / "y")
    (tmp_path / "exists").mkdir()
    with pytest.raises(FileExistsError):
        apply_bug(bugs[0], GOLDEN, tmp_path / "exists")


def test_crlf_golden_files_are_patched_the_same(bugs, tmp_path):
    """골든이 CRLF(Windows)여도 같은 줄에 같은 패치가 적용된다."""
    crlf = tmp_path / "crlf"
    crlf.mkdir()
    for p in GOLDEN.glob("*.v"):
        (crlf / p.name).write_bytes(p.read_text(encoding="utf-8", errors="replace")
                                    .replace("\n", "\r\n").encode("utf-8"))
    for b in bugs[:6]:
        a1 = apply_bug(b, GOLDEN, tmp_path / f"lf_{b.id}")
        a2 = apply_bug(b, crlf, tmp_path / f"crlf_{b.id}")
        assert a1.line == a2.line and a1.diff.replace("\r", "") == a2.diff.replace("\r", "")


def test_load_catalog_rejects_bad_schema(tmp_path):
    """필수 키 누락, 알 수 없는 유형, id 중복, 범위 밖 occurrence는 로드 시점에 거부한다."""
    good = json.loads(CATALOG.read_text(encoding="utf-8"))["bugs"][0]

    def load(entries):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"bugs": entries}), encoding="utf-8")
        return load_catalog(p)

    with pytest.raises(ValueError):
        load([{k: v for k, v in good.items() if k != "file"}])
    with pytest.raises(ValueError):
        load([{**good, "type": "nonsense"}])
    with pytest.raises(ValueError):
        load([good, good])
    with pytest.raises(ValueError):
        load([{**good, "occurrence": good["expect_count"] + 1}])


def test_catalog_json_is_consistent_with_golden_top_name():
    """카탈로그의 골든 경로와 top 모듈 이름이 실제 파일과 일치한다 (4-3 하네스가 그대로 사용)."""
    meta = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert (ROOT / meta["golden_rtl"]).is_dir()
    tb = (ROOT / "dut" / "sync_fifo" / "tb" / "tb_sync_fifo_sc.v").read_text(encoding="utf-8", errors="replace")
    assert f"module {meta['top']}" in tb