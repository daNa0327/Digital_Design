"""sim/xsim.py의 XsimSim 검증.

앞의 6개는 run_tool을 가짜로 바꿔(monkeypatch) 조율 로직만 검증한다:
단계 순서, 중단 정책, 입력 검증, 생성 파일.
마지막 1개는 실제 Vivado로 끝까지 실행한다 (Vivado가 없으면 건너뜀).
"""

import shutil
from pathlib import Path

import pytest

from core.models import StepResult
from sim.xsim import XsimSim


def _fake_run_tool(returncodes: dict[str, int]):
    """단계 이름별 종료 코드를 돌려주는 가짜 run_tool과, 호출된 단계 기록 리스트를 만든다."""
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
    """내용이 중요하지 않은 최소 소스 파일 하나."""
    p = tmp_path / "a.v"
    p.write_text("module a; endmodule\n")
    return p


def test_all_steps_run_in_order(tmp_path, src, monkeypatch):
    """모두 성공하면 xvlog -> xelab -> xsim 순서로 실행되고 중단 기록은 없다."""
    fake, calls = _fake_run_tool({})
    monkeypatch.setattr("sim.xsim.run_tool", fake)
    res = XsimSim().run([str(src)], "a", str(tmp_path / "w1"))
    assert calls == ["xvlog", "xelab", "xsim"]
    assert res.stopped_at is None


def test_stops_after_xvlog_failure(tmp_path, src, monkeypatch):
    """xvlog가 실패하면 xelab 이후는 실행하지 않는다 (실패한 컴파일 위의 파생 에러 방지)."""
    fake, calls = _fake_run_tool({"xvlog": 1})
    monkeypatch.setattr("sim.xsim.run_tool", fake)
    res = XsimSim().run([str(src)], "a", str(tmp_path / "w1"))
    assert calls == ["xvlog"]               # xelab은 실행되지 않아야 함
    assert res.stopped_at == "xvlog"


def test_stops_after_xelab_failure(tmp_path, src, monkeypatch):
    """xelab이 실패하면 xsim은 실행하지 않는다."""
    fake, calls = _fake_run_tool({"xelab": 1})
    monkeypatch.setattr("sim.xsim.run_tool", fake)
    res = XsimSim().run([str(src)], "a", str(tmp_path / "w1"))
    assert calls == ["xvlog", "xelab"]
    assert res.stopped_at == "xelab"


def test_missing_source_raises(tmp_path):
    """소스 파일이 없으면 호출 측 실수이므로 FileNotFoundError (DUT 결과가 아님)."""
    with pytest.raises(FileNotFoundError):
        XsimSim().run([str(tmp_path / "nope.v")], "a", str(tmp_path / "w1"))


def test_existing_workdir_raises(tmp_path, src):
    """이미 있는 작업 폴더는 거부한다 (이전 xsim.dir 재사용으로 에러가 가려지는 것을 방지)."""
    (tmp_path / "w1").mkdir()
    with pytest.raises(FileExistsError):
        XsimSim().run([str(src)], "a", str(tmp_path / "w1"))


def test_generated_files(tmp_path, src, monkeypatch):
    """files.f(절대경로), run.tcl(VCD 덤프 명령)이 만들어지고 RunResult.sources에 입력 소스가 기록된다."""
    fake, _ = _fake_run_tool({})
    monkeypatch.setattr("sim.xsim.run_tool", fake)
    wd = tmp_path / "w1"
    res = XsimSim().run([str(src)], "a", str(wd))
    assert [Path(s).name for s in res.sources] == ["a.v"]
    listed = (wd / "files.f").read_text(encoding="utf-8").split()
    assert len(listed) == 1 and Path(listed[0]).samefile(src)
    tcl = (wd / "run.tcl").read_text(encoding="utf-8")
    assert "open_vcd dump.vcd" in tcl and "run all" in tcl
    


@pytest.mark.skipif(shutil.which("xvlog") is None, reason="Vivado 없음")
def test_async_fifo_end_to_end(tmp_path):
    """실제 Vivado로 async FIFO를 끝까지 실행: 세 단계 모두 종료 코드 0, 402ns에 $finish, VCD 생성."""
    root = Path(__file__).resolve().parents[1] / "Manual_test"
    names = ["async_fifo.v", "bin2gray.v", "fifo_ctrl.v", "fifo_mem.v", "synchronizer.v"]
    files = [str(root / "dut" / n) for n in names] + [str(root / "tb" / "tb_async_fifo.v")]
    res = XsimSim().run(files, "async_fifo_tb", str(tmp_path / "run"))
    assert res.stopped_at is None
    assert [s.returncode for s in res.steps] == [0, 0, 0]
    assert "$finish called at time : 402 ns" in res.steps[-1].stdout
    assert res.vcd_path is not None
