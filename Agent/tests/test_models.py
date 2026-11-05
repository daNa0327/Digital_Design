from core.models import StepResult, RunResult

def test_step_result_defaults():
    # 선택 필드(timed_out)의 기본값이 False인가
    s = StepResult(name="xvlog", cmd=["xvlog"], returncode=0,
                   stdout="ok", duration_s=0.1)
    assert s.timed_out is False

def test_run_result_steps_not_shared():
    # 두 RunResult가 steps 리스트를 따로 갖는가
    a = RunResult(workdir="a")
    b = RunResult(workdir="b")
    a.steps.append(
        StepResult(name="xvlog", cmd=[], returncode=1, stdout="", duration_s=0.0)
    )
    assert b.steps == []        # a에 추가해도 b는 비어 있어야 함


from core.models import ErrorItem, SimResult

def test_sim_result_defaults():
    r = SimResult(status="PASS")
    assert r.errors == [] and r.unanalyzed_files == []
    assert r.finish_time_ps is None and r.tb_verdict is None


def test_error_item_optional_fields():
    e = ErrorItem(stage="xelab", code=None, message="no location")
    assert e.file is None and e.line is None
    assert e.is_primary is False