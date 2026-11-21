"""골든 DUT(sync_fifo)와 self-checking TB 검증 (Vivado가 없으면 건너뜀).

평가 세트의 기준선이 맞아야 이후 버그 탐지율이 의미가 있다.
  - 골든 DUT는 PASS여야 한다 (TB가 정상 DUT를 FAIL로 오판하지 않음)
  - 명백한 버그를 넣으면 FAIL이어야 한다 (TB가 최소한의 감도를 가짐)
"""

import shutil
from pathlib import Path

import pytest

from core.analyzer import analyze
from sim.xsim import XsimSim

ROOT = Path(__file__).resolve().parents[1] / "dut" / "sync_fifo"
RTL_NAMES = ("sync_fifo.v", "fifo_ctrl.v", "fifo_mem.v")
TB = ROOT / "tb" / "tb_sync_fifo_sc.v"
TOP = "sync_fifo_sc_tb"

needs_vivado = pytest.mark.skipif(shutil.which("xvlog") is None, reason="Vivado 없음")


def _files(rtl_dir: Path) -> list[str]:
    return [str(rtl_dir / n) for n in RTL_NAMES] + [str(TB)]


@needs_vivado
def test_golden_dut_passes(tmp_path):
    """골든 DUT는 PASS이고 TB가 PASS를 직접 출력했으며 에러와 미분석 파일이 없다."""
    res = analyze(XsimSim().run(_files(ROOT / "rtl"), TOP, str(tmp_path / "run")))
    assert res.status == "PASS" and res.tb_verdict == "PASS"
    assert res.errors == [] and res.unanalyzed_files == []
    assert res.vcd_path is not None


@needs_vivado
def test_tb_detects_obvious_mutant(tmp_path):
    """full 기준을 8에서 7로 바꾼 변형본은 TB가 FAIL로 잡아야 한다."""
    rtl = tmp_path / "rtl"
    shutil.copytree(ROOT / "rtl", rtl)
    src = (rtl / "fifo_ctrl.v").read_text(encoding="utf-8", errors="replace")
    assert src.count("count == 8)") == 1, "fifo_ctrl.v의 full 조건 형식이 바뀌었습니다"
    (rtl / "fifo_ctrl.v").write_text(src.replace("count == 8)", "count == 7)"), encoding="utf-8")

    res = analyze(XsimSim().run(_files(rtl), TOP, str(tmp_path / "run")))
    assert res.status == "FAIL" and res.tb_verdict == "FAIL"