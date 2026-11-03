import os
import subprocess
import sys
import time

import pytest

from sim.runner import run_tool

def test_run_tool_missing_executable(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_tool("definitely_not_a_real_tool_xyz", [], cwd=str(tmp_path))

def test_nonzero_returncode_is_recorded_not_raised(tmp_path):
    r = run_tool(sys.executable, ["-c", "import sys; sys.exit(3)"], cwd=str(tmp_path))
    assert r.returncode == 3

def test_stdout_and_stderr_are_merged(tmp_path):
    code = "import sys; print('out'); print('err', file=sys.stderr)"
    r = run_tool(sys.executable, ["-c", code], cwd=str(tmp_path))
    assert "out" in r.stdout and "err" in r.stdout

def test_cwd_is_applied(tmp_path):
    r = run_tool(sys.executable, ["-c", "import os; print(os.getcwd())"], cwd=str(tmp_path))
    assert os.path.samefile(r.stdout.strip(), tmp_path)

_CHILD = "import time; time.sleep(60)"
_PARENT = (
    "import subprocess, sys, time;"
    f"p = subprocess.Popen([sys.executable, '-c', {_CHILD!r}]);"
    "print(p.pid, flush=True);"
    "time.sleep(60)"
)

@pytest.mark.skipif(os.name != "nt", reason="Windows 프로세스 트리 종료 테스트")
def test_timeout_kills_process_tree(tmp_path):
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
    r = run_tool(sys.executable, ["-c", "print('ok')"], cwd=str(tmp_path), timeout=30)
    assert r.timed_out is False
    assert r.returncode == 0