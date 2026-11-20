"""sim/runner.py의 run_tool() 검증.

Vivado 없이도 돌도록 파이썬 인터프리터(sys.executable)를 외부 도구 대역으로 사용한다.
"""

import os
import subprocess
import sys
import time

import pytest

from sim.runner import run_tool


def test_run_tool_missing_executable(tmp_path):
    """PATH에 없는 도구는 결과 객체가 아니라 FileNotFoundError (환경 문제와 DUT 결과를 구분)."""
    with pytest.raises(FileNotFoundError):
        run_tool("definitely_not_a_real_tool_xyz", [], cwd=str(tmp_path))


def test_nonzero_returncode_is_recorded_not_raised(tmp_path):
    """종료 코드가 0이 아니어도 예외 없이 기록된다 (종료 코드 1은 수집할 데이터)."""
    r = run_tool(sys.executable, ["-c", "import sys; sys.exit(3)"], cwd=str(tmp_path))
    assert r.returncode == 3


def test_stdout_and_stderr_are_merged(tmp_path):
    """stdout과 stderr가 하나의 문자열로 합쳐진다 (터미널에서 본 순서를 보존)."""
    code = "import sys; print('out'); print('err', file=sys.stderr)"
    r = run_tool(sys.executable, ["-c", code], cwd=str(tmp_path))
    assert "out" in r.stdout and "err" in r.stdout


def test_cwd_is_applied(tmp_path):
    """지정한 작업 폴더에서 실행된다 (로그와 xsim.dir이 workdir 안에 생기는 격리의 전제)."""
    r = run_tool(sys.executable, ["-c", "import os; print(os.getcwd())"], cwd=str(tmp_path))
    assert os.path.samefile(r.stdout.strip(), tmp_path)


# 부모 프로세스가 60초짜리 자식을 띄우고 자기 PID를 출력한 뒤 대기한다.
# ".BAT 래퍼 -> xsim.exe" 구조(래퍼만 죽이면 자식이 남는 상황)를 흉내 낸 것.
_CHILD = "import time; time.sleep(60)"
_PARENT = (
    "import subprocess, sys, time;"
    f"p = subprocess.Popen([sys.executable, '-c', {_CHILD!r}]);"
    "print(p.pid, flush=True);"
    "time.sleep(60)"
)


@pytest.mark.skipif(os.name != "nt", reason="Windows 프로세스 트리 종료 테스트")
def test_timeout_kills_process_tree(tmp_path):
    """타임아웃이 나면 부모뿐 아니라 자식 프로세스까지 종료하고, 종료 코드는 None으로 기록한다."""
    start = time.perf_counter()
    r = run_tool(sys.executable, ["-c", _PARENT], cwd=str(tmp_path), timeout=3)
    elapsed = time.perf_counter() - start

    assert r.timed_out is True
    assert r.returncode is None
    assert elapsed < 15                    # 60초를 기다리지 않고 끝나야 함

    child_pid = r.stdout.split()[0]        # 부모가 출력한 자식 PID
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {child_pid}"],
        capture_output=True, text=True, errors="replace",
    ).stdout
    assert child_pid not in out            # 자식이 남아 있지 않아야 함


def test_timeout_not_triggered_for_fast_process(tmp_path):
    """제한 시간 안에 끝나는 프로세스는 타임아웃으로 처리되지 않는다."""
    r = run_tool(sys.executable, ["-c", "print('ok')"], cwd=str(tmp_path), timeout=30)
    assert r.timed_out is False
    assert r.returncode == 0
