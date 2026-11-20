"""core/models.py의 데이터 모델 기본 동작 검증 (Vivado 불필요).

StepResult / RunResult는 Phase 1의 원본 사실, ErrorItem / SimResult는 Phase 2의 해석 결과를 담는다.
"""

from core.models import ErrorItem, RunResult, SimResult, StepResult


def test_step_result_defaults():
    """StepResult의 timed_out 기본값은 False (타임아웃이 아니면 정상 경로로 본다)."""
    s = StepResult(name="xvlog", cmd=["xvlog"], returncode=0,
                   stdout="ok", duration_s=0.1)
    assert s.timed_out is False


def test_run_result_steps_not_shared():
    """RunResult마다 steps 리스트가 따로 만들어진다 (가변 기본값을 공유하지 않음)."""
    a = RunResult(workdir="a")
    b = RunResult(workdir="b")
    a.steps.append(
        StepResult(name="xvlog", cmd=[], returncode=1, stdout="", duration_s=0.0)
    )
    assert b.steps == []        # a에 추가해도 b는 비어 있어야 함


def test_sim_result_defaults():
    """SimResult는 status만 주면 만들어지고, 나머지는 비어 있는 기본값을 가진다."""
    r = SimResult(status="PASS")
    assert r.errors == [] and r.unanalyzed_files == []
    assert r.finish_time_ps is None and r.tb_verdict is None


def test_error_item_optional_fields():
    """위치 정보(file, line)가 없는 에러도 표현할 수 있고, 주 원인 표시는 기본 False."""
    e = ErrorItem(stage="xelab", code=None, message="no location")
    assert e.file is None and e.line is None
    assert e.is_primary is False


def test_error_item_runtime_defaults():
    """시뮬레이터 런타임 에러용 필드(severity, time_ps)의 기본값: ERROR, 시각 없음."""
    e = ErrorItem(stage="xsim", code=None, message="m")
    assert e.severity == "ERROR" and e.time_ps is None


def test_sim_result_failed_stage_default():
    """실패하지 않은 결과는 failed_stage가 None이다."""
    assert SimResult(status="PASS").failed_stage is None
