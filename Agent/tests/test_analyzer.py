from pathlib import Path

import pytest

from core.analyzer import analyze
from core.log_parser import parse_xvlog
from core.models import RunResult, StepResult

DATA = Path(__file__).parent / "data"


def read(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8", errors="replace")


def step(name: str, text: str, rc: int = 0, timed_out: bool = False) -> StepResult:
    return StepResult(
        name=name, cmd=[name],
        returncode=None if timed_out else rc,
        stdout=text, duration_s=0.0, timed_out=timed_out,
    )


OK_SOURCES = parse_xvlog(read("xvlog_ok.log")).attempted_files


def run_with_xsim(sample: str, **kw) -> RunResult:
    return RunResult(
        workdir="w",
        steps=[
            step("xvlog", read("xvlog_ok.log")),
            step("xelab", read("xelab_ok.log")),
            step("xsim", read(sample), **kw),
        ],
        vcd_path="w/dump.vcd",
        sources=OK_SOURCES,
    )


def test_no_marker_is_no_verdict():
    res = analyze(run_with_xsim("xsim_ok.log"))
    assert res.status == "NO_VERDICT"
    assert res.errors == [] and res.unanalyzed_files == []
    assert res.finish_time_ps == 402_000
    assert res.tb_verdict is None and res.failed_stage is None


def test_pass_marker_is_pass():
    res = analyze(run_with_xsim("xsim_pass_marker.log"))
    assert res.status == "PASS" and res.tb_verdict == "PASS"
    assert res.errors == []


def test_fail_marker_is_fail():
    res = analyze(run_with_xsim("xsim_fail_marker.log"))
    assert res.status == "FAIL" and res.tb_verdict == "FAIL"
    assert res.failed_stage == "xsim"
    assert len(res.errors) == 1
    e = res.errors[0]
    assert e.code == "TB_FAIL" and e.message == "dummy check" and e.is_primary


def test_sim_error_is_fail_even_without_marker():
    res = analyze(run_with_xsim("xsim_error.log"))        # xsim 종료 코드는 0
    assert res.status == "FAIL" and res.tb_verdict is None
    assert [e.severity for e in res.errors] == ["ERROR"]


def test_fatal_is_fail():
    res = analyze(run_with_xsim("xsim_fatal.log"))
    assert res.status == "FAIL"
    assert [e.severity for e in res.errors] == ["FATAL"]


def test_pass_marker_with_error_is_fail():
    res = analyze(run_with_xsim("xsim_pass_with_error.log"))
    assert res.status == "FAIL"
    assert res.tb_verdict == "PASS"        # TB가 한 말과 종합 판정은 다를 수 있다


def test_hang_is_timeout():
    res = analyze(run_with_xsim("xsim_hang.log", timed_out=True))
    assert res.status == "TIMEOUT" and res.failed_stage == "xsim"
    assert res.finish_time_ps is None


def test_compile_error():
    err_files = parse_xvlog(read("xvlog_syntax_error.log")).attempted_files
    run = RunResult(
        workdir="w",
        steps=[step("xvlog", read("xvlog_syntax_error.log"), rc=1)],
        stopped_at="xvlog",
        sources=err_files + OK_SOURCES[4:],      # 에러 파일 뒤의 두 파일은 분석되지 못함
    )
    res = analyze(run)
    assert res.status == "COMPILE_ERROR" and res.failed_stage == "xvlog"
    assert len(res.errors) == 3 and res.errors[0].is_primary
    assert [Path(f).name for f in res.unanalyzed_files] == [
        "synchronizer.v", "tb_async_fifo.v",
    ]


def test_elab_error():
    run = RunResult(
        workdir="w",
        steps=[
            step("xvlog", read("xvlog_ok.log")),
            step("xelab", read("xelab_missing_top.log"), rc=1),
        ],
        stopped_at="xelab",
        sources=OK_SOURCES,
    )
    res = analyze(run)
    assert res.status == "ELAB_ERROR" and res.failed_stage == "xelab"
    assert res.errors[0].code == "XSIM 43-3225"


def test_nonzero_exit_without_error_line_gets_synthetic_error():
    res = analyze(RunResult(workdir="w", steps=[step("xvlog", "", rc=1)]))
    assert res.status == "COMPILE_ERROR"
    assert [e.code for e in res.errors] == ["EXIT_CODE"]


def test_xelab_without_snapshot_is_elab_error():
    run = RunResult(workdir="w", steps=[
        step("xvlog", read("xvlog_ok.log")),
        step("xelab", "Starting static elaboration\n", rc=0),
    ])
    res = analyze(run)
    assert res.status == "ELAB_ERROR"
    assert [e.code for e in res.errors] == ["NO_SNAPSHOT"]


def test_xsim_nonzero_exit_is_fail():
    res = analyze(run_with_xsim("xsim_ok.log", rc=1))
    assert res.status == "FAIL"
    assert [e.code for e in res.errors] == ["EXIT_CODE"]
    assert res.errors[0].is_primary


def test_empty_steps_raises():
    with pytest.raises(ValueError):
        analyze(RunResult(workdir="w"))