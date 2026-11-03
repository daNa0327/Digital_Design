import os
import shutil
import subprocess
import time

from core.models import StepResult


def _kill_tree(proc: subprocess.Popen) -> None:
    """proc과 그 자식 프로세스 전체를 강제 종료한다."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.kill()   # 현재는 Windows 기준. 다른 OS는 필요해지면 보강


def run_tool(
    name: str,
    args: list[str],
    cwd: str,
    timeout: float | None = None,
) -> StepResult:
    exe = shutil.which(name)
    if exe is None:
        raise FileNotFoundError(
            f"'{name}'을(를) PATH에서 찾을 수 없습니다. "
            "Vivado 2024.2 bin 폴더가 PATH에 있는지 확인하세요."
        )

    cmd = [exe, *args]
    start = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )

    timed_out = False
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        stdout, _ = proc.communicate()   # 죽인 뒤 남은 출력을 거둔다

    duration = time.perf_counter() - start

    return StepResult(
        name=name,
        cmd=cmd,
        returncode=None if timed_out else proc.returncode,
        stdout=stdout or "",
        duration_s=duration,
        timed_out=timed_out,
    )