import shutil
from pathlib import Path

import pytest

from core.analyzer import analyze
from sim.xsim import XsimSim

MT = Path(__file__).resolve().parents[1] / "Manual_test"
DUT_NAMES = ("async_fifo.v", "bin2gray.v", "fifo_ctrl.v", "fifo_mem.v", "synchronizer.v")
TB = str(MT / "tb" / "tb_async_fifo.v")

needs_vivado = pytest.mark.skipif(shutil.which("xvlog") is None, reason="Vivado 없음")


@needs_vivado
def test_real_run_without_marker_is_no_verdict(tmp_path):
    files = [str(MT / "dut" / n) for n in DUT_NAMES] + [TB]
    run = XsimSim().run(files, "async_fifo_tb", str(tmp_path / "run"))
    res = analyze(run)
    assert res.status == "NO_VERDICT"
    assert res.errors == [] and res.unanalyzed_files == []
    assert res.finish_time_ps == 402_000
    assert res.vcd_path is not None


@needs_vivado
def test_real_compile_error_reports_unanalyzed_files(tmp_path):
    src = (MT / "dut" / "fifo_mem.v").read_text(encoding="utf-8", errors="replace")
    assert "mem[wr_addr] <= data_in;" in src, "fifo_mem.v의 쓰기 줄 형식이 바뀌었습니다"
    broken = tmp_path / "fifo_mem.v"
    broken.write_text(src.replace("mem[wr_addr] <= data_in;", "mem[wr_addr] <= data_in"),
                      encoding="utf-8")

    files = [
        str(MT / "dut" / "async_fifo.v"), str(MT / "dut" / "bin2gray.v"),
        str(MT / "dut" / "fifo_ctrl.v"), str(broken),
        str(MT / "dut" / "synchronizer.v"), TB,
    ]
    run = XsimSim().run(files, "async_fifo_tb", str(tmp_path / "run"))
    res = analyze(run)

    assert run.stopped_at == "xvlog"
    assert res.status == "COMPILE_ERROR" and res.failed_stage == "xvlog"
    assert res.errors[0].is_primary
    assert Path(res.errors[0].file).name == "fifo_mem.v"
    assert [Path(f).name for f in res.unanalyzed_files] == [
        "synchronizer.v", "tb_async_fifo.v",
    ]