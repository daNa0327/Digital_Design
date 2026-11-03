import shutil
from pathlib import Path

import pytest

from core.models import StepResult
from sim.xsim import XsimSim

def _fake_run_tool(returncodes: dict[str, int]):
    calls: list[str] = []

    def fake(name, args, cwd, timeout=None):
        calls.append(name)
        return StepResult(
            name=name, cmd=[name, *args],
            returncode=returncodes.get(name, 0),
            stdout="", duration_s=0.0,
        )

    return fake, calls

@pytest.fixture
def src(tmp_path):
    p = tmp_path / "a.v"
    p.write_text("module a; endmodule\n")
    return p

def test_all_steps_run_in_order(tmp_path, src, monkeypatch):
    fake, calls = _fake_run_tool({})
    monkeypatch.setattr("sim.xsim.run_tool", fake)
    res = XsimSim().run([str(src)], "a", str(tmp_path / "w1"))
    assert calls == ["xvlog", "xelab", "xsim"]
    assert res.stopped_at is None

def test_stops_after_xvlog_failure(tmp_path, src, monkeypatch):
    fake, calls = _fake_run_tool({"xvlog": 1})
    monkeypatch.setattr("sim.xsim.run_tool", fake)
    res = XsimSim().run([str(src)], "a", str(tmp_path / "w1"))
    assert calls == ["xvlog"]               # xelab은 실행되지 않아야 함
    assert res.stopped_at == "xvlog"

def test_stops_after_xelab_failure(tmp_path, src, monkeypatch):
    fake, calls = _fake_run_tool({"xelab": 1})
    monkeypatch.setattr("sim.xsim.run_tool", fake)
    res = XsimSim().run([str(src)], "a", str(tmp_path / "w1"))
    assert calls == ["xvlog", "xelab"]
    assert res.stopped_at == "xelab"

def test_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        XsimSim().run([str(tmp_path / "nope.v")], "a", str(tmp_path / "w1"))

def test_existing_workdir_raises(tmp_path, src):
    (tmp_path / "w1").mkdir()
    with pytest.raises(FileExistsError):
        XsimSim().run([str(src)], "a", str(tmp_path / "w1"))

def test_generated_files(tmp_path, src, monkeypatch):
    fake, _ = _fake_run_tool({})
    monkeypatch.setattr("sim.xsim.run_tool", fake)
    wd = tmp_path / "w1"
    XsimSim().run([str(src)], "a", str(wd))
    listed = (wd / "files.f").read_text(encoding="utf-8").split()
    assert len(listed) == 1 and Path(listed[0]).samefile(src)
    tcl = (wd / "run.tcl").read_text(encoding="utf-8")
    assert "open_vcd dump.vcd" in tcl and "run all" in tcl

@pytest.mark.skipif(shutil.which("xvlog") is None, reason="Vivado 없음")
def test_async_fifo_end_to_end(tmp_path):
    root = Path(__file__).resolve().parents[1] / "Manual_test"
    names = ["async_fifo.v", "bin2gray.v", "fifo_ctrl.v", "fifo_mem.v", "synchronizer.v"]
    files = [str(root / "dut" / n) for n in names] + [str(root / "tb" / "tb_async_fifo.v")]
    res = XsimSim().run(files, "async_fifo_tb", str(tmp_path / "run"))
    assert res.stopped_at is None
    assert [s.returncode for s in res.steps] == [0, 0, 0]
    assert "$finish called at time : 402 ns" in res.steps[-1].stdout
    assert res.vcd_path is not None