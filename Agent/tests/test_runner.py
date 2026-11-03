import os
import sys

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