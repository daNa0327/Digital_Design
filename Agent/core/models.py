'''
xvlog, xelab, xsim 각 단계가 남긴 원본 사실을 담는 틀

단계마다 종료 코드가 있음 (정상 0, 에러 1)	returncode
출력이 콘솔과 로그 파일에서 동일함	        stdout
에러가 나면 다음 단계를 실행하지 않기로 함	 stopped_at
VCD는 있을 때만 생김	                 vcd_path (없으면 None)
'''

from dataclasses import dataclass, field

@dataclass
class StepResult:
    # 도구 한 단계(xvlog / xelab / xsim)의 실행 결과 (원본 사실만).
    name: str
    cmd: list[str]
    returncode: int | None      # 타임아웃으로 강제 종료했다면 None
    stdout: str                 # stdout + stderr 합친 출력
    duration_s: float
    timed_out: bool = False

@dataclass
class RunResult:
    # 한 번의 전체 실행(xvlog → xelab → xsim) 결과.
    workdir: str
    steps: list[StepResult] = field(default_factory=list)
    stopped_at: str | None = None   # 중단 정책으로 멈춘 단계 이름
    vcd_path: str | None = None
    total_duration_s: float = 0.0