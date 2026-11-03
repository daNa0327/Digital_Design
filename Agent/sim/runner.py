import shutil
import subprocess
import time

from core.models import StepResult

def run_tool(name: str, args: list[str], cwd: str) -> StepResult:
    exe = shutil.which(name)
    if exe is None:
        raise FileNotFoundError(
            f"'{name}'을(를) PATH에서 찾을 수 없습니다. "
            "Vivado 2024.2 bin 폴더가 PATH에 있는지 확인하세요."
        )

    cmd = [exe, *args]
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,       # 출력을 파이썬이 받는다
        stderr=subprocess.STDOUT,     # stderr를 stdout에 합친다 (출력 순서 유지)
        text=True,                    # 바이트가 아닌 문자열로 받는다
        errors="replace",             # 디코딩 불가 문자가 있어도 죽지 않는다
        check=False,                  # 종료 코드가 0이 아니어도 예외를 내지 않는다
    )
    duration = time.perf_counter() - start

    return StepResult(
        name=name,
        cmd=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        duration_s=duration,
    )