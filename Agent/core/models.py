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
    stage: str                  # "xvlog" | "xelab" | "xsim" 어느 도구가 낸 에러인지
    code: str | None            # 예: "VRFC 10-4982"
    message: str
    file: str | None = None     # 에러 위치
    line: int | None = None     # 에러 위치
    is_primary: bool = False    # 같은 단계의 첫 에러만 True

@dataclass
class SimResult:
    # RunResult를 해석한 최종 결과.
    status: Status      # 최종 판정
    errors: list[ErrorItem] = field(default_factory=list)       # 에러 목록
    unanalyzed_files: list[str] = field(default_factory=list)   # 분석하지 못한 파일
    finish_time_ps: int | None = None   # 로그의 $finish 시각
    tb_verdict: Literal["PASS", "FAIL"] | None = None           # TB가 출력한 PASS/FAIL 원본 마커
    workdir: str | None = None          # 파일 경로
    vcd_path: str | None = None         # 파일 경로
    # TB가 PASS를 출력했어도 시뮬레이터가 ERROR를 냈다면 status는 FAIL
#---------------------------------------#