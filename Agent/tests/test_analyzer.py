"""core/analyzer.py의 analyze(RunResult) -> SimResult 판정 규칙 검증.

실제 로그 샘플(tests/data)로 RunResult를 조립해서 넣는다. Vivado는 필요 없다.

판정 우선순위 (위에서 아래로 처음 해당하는 것):
  1. 어느 단계든 타임아웃            -> TIMEOUT
  2. xvlog 실패(종료 코드 또는 ERROR) -> COMPILE_ERROR
  3. xelab 실패(종료 코드, ERROR, 스냅샷 없음) -> ELAB_ERROR
  4. xsim 종료 코드 이상, Error/Fatal, [TB] FAIL -> FAIL   (xsim 종료 코드는 에러가 있어도 0이므로 로그로 판정)
  5. [TB] PASS 마커가 있음            -> PASS
  6. 그 외(끝까지 돌았지만 마커 없음)  -> NO_VERDICT
"""

from pathlib import Path

import pytest

from core.analyzer import analyze
from core.log_parser import parse_xvlog
from core.models import RunResult, StepResult

DATA = Path(__file__).parent / "data"


def read(name: str) -> str:
    """tests/data의 샘플 로그를 텍스트로 읽는다."""
    return (DATA / name).read_text(encoding="utf-8", errors="replace")


def step(name: str, text: str, rc: int = 0, timed_out: bool = False) -> StepResult:
    """샘플 텍스트로 StepResult를 만든다 (타임아웃이면 종료 코드는 None)."""
    return StepResult(
        name=name, cmd=[name],
        returncode=None if timed_out else rc,
        stdout=text, duration_s=0.0, timed_out=timed_out,
    )


OK_SOURCES = parse_xvlog(read("xvlog_ok.log")).attempted_files


def run_with_xsim(sample: str, **kw) -> RunResult:
    """xvlog, xelab은 정상 샘플로 고정하고 xsim 단계만 sample로 바꾼 RunResult."""
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
    """끝까지 정상 종료했지만 PASS/FAIL 마커가 없으면 NO_VERDICT (self-checking이 아닌 TB의 정상 실행)."""
    res = analyze(run_with_xsim("xsim_ok.log"))
    assert res.status == "NO_VERDICT"
    assert res.errors == [] and res.unanalyzed_files == []
    assert res.finish_time_ps == 402_000
    assert res.tb_verdict is None and res.failed_stage is None


def test_pass_marker_is_pass():
    """명시적 [TB] PASS 마커가 있고 에러가 없으면 PASS."""
    res = analyze(run_with_xsim("xsim_pass_marker.log"))
    assert res.status == "PASS" and res.tb_verdict == "PASS"
    assert res.errors == []


def test_fail_marker_is_fail():
    """[TB] FAIL 마커는 FAIL이 되고, 그 문구가 TB_FAIL 에러로 에러 목록에 들어간다."""
    res = analyze(run_with_xsim("xsim_fail_marker.log"))
    assert res.status == "FAIL" and res.tb_verdict == "FAIL"
    assert res.failed_stage == "xsim"
    assert len(res.errors) == 1
    e = res.errors[0]
    assert e.code == "TB_FAIL" and e.message == "dummy check" and e.is_primary


def test_sim_error_is_fail_even_without_marker():
    """$error가 있으면 마커가 없어도 FAIL (xsim 종료 코드는 0이어도 로그로 잡는다)."""
    res = analyze(run_with_xsim("xsim_error.log"))        # xsim 종료 코드는 0
    assert res.status == "FAIL" and res.tb_verdict is None
    assert [e.severity for e in res.errors] == ["ERROR"]


def test_fatal_is_fail():
    """$fatal은 심각도 FATAL로 기록되고 FAIL이 된다 ($finish 줄이 있어도 성공이 아님)."""
    res = analyze(run_with_xsim("xsim_fatal.log"))
    assert res.status == "FAIL"
    assert [e.severity for e in res.errors] == ["FATAL"]


def test_pass_marker_with_error_is_fail():
    """TB는 PASS라고 했지만 시뮬레이터 에러가 있으면 최종은 FAIL (tb_verdict와 status는 다를 수 있다)."""
    res = analyze(run_with_xsim("xsim_pass_with_error.log"))
    assert res.status == "FAIL"
    assert res.tb_verdict == "PASS"        # TB가 한 말과 종합 판정은 다를 수 있다


def test_hang_is_timeout():
    """xsim 단계가 타임아웃이면 TIMEOUT이고 어느 단계인지(failed_stage)를 기록한다."""
    res = analyze(run_with_xsim("xsim_hang.log", timed_out=True))
    assert res.status == "TIMEOUT" and res.failed_stage == "xsim"
    assert res.finish_time_ps is None


def test_compile_error():
    """컴파일 에러: COMPILE_ERROR, 에러 3건(첫 건이 주 원인), 에러 파일 뒤의 미분석 파일 2개를 알려 준다."""
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
    """xelab이 top을 못 찾으면 ELAB_ERROR이고 에러 코드가 그대로 전달된다."""
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
    """종료 코드는 비정상인데 ERROR 줄이 없으면 EXIT_CODE 합성 에러로 이유를 채운다."""
    res = analyze(RunResult(workdir="w", steps=[step("xvlog", "", rc=1)]))
    assert res.status == "COMPILE_ERROR"
    assert [e.code for e in res.errors] == ["EXIT_CODE"]


def test_xelab_without_snapshot_is_elab_error():
    """xelab이 종료 코드 0이어도 스냅샷이 안 만들어졌으면 ELAB_ERROR (NO_SNAPSHOT 합성 에러)."""
    run = RunResult(workdir="w", steps=[
        step("xvlog", read("xvlog_ok.log")),
        step("xelab", "Starting static elaboration\n", rc=0),
    ])
    res = analyze(run)
    assert res.status == "ELAB_ERROR"
    assert [e.code for e in res.errors] == ["NO_SNAPSHOT"]


def test_xsim_nonzero_exit_is_fail():
    """xsim 종료 코드가 0이 아니면 FAIL (아직 관측한 적 없는 경우에 대한 예방적 규칙)."""
    res = analyze(run_with_xsim("xsim_ok.log", rc=1))
    assert res.status == "FAIL"
    assert [e.code for e in res.errors] == ["EXIT_CODE"]
    assert res.errors[0].is_primary


def test_empty_steps_raises():
    """실행 기록이 비어 있는 RunResult는 해석할 수 없으므로 ValueError."""
    with pytest.raises(ValueError):
        analyze(RunResult(workdir="w"))
