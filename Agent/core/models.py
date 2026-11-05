'''
Phase 1                          Phase 2
XsimSim.run() ──▶ RunResult ──▶ analyze() ──▶ SimResult
                  (원본 사실)     (규칙, 정규식)   (해석된 결과)
'''
from dataclasses import dataclass, field
from typing import Literal

#---------- Phase 1: 원본 사실 ----------#
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
#---------------------------------------#

#---------- Phase 2: 해석 결과 ----------#
Status = Literal[
    "PASS", "FAIL", "NO_VERDICT", "COMPILE_ERROR", "ELAB_ERROR", "TIMEOUT"
]

@dataclass
class ErrorItem:
    # 로그에서 뽑은 에러 한 건.
    stage: str                  # "xvlog" | "xelab" | "xsim"
    code: str | None            # 예: "VRFC 10-4982"
    message: str
    file: str | None = None
    line: int | None = None
    is_primary: bool = False    # 같은 단계의 첫 에러만 True

@dataclass
class SimResult:
    # RunResult를 해석한 최종 결과.
    status: Status
    errors: list[ErrorItem] = field(default_factory=list)
    unanalyzed_files: list[str] = field(default_factory=list)
    finish_time_ps: int | None = None
    tb_verdict: Literal["PASS", "FAIL"] | None = None
    workdir: str | None = None
    vcd_path: str | None = None
#---------------------------------------#