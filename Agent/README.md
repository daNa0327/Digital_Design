# RTL Verification AI Agent
RTL 검증 업무를 자동화하는 AI Agent 프로젝트입니다.

RTL을 입력하면 **Testbench 생성 → 시뮬레이션 → 로그 분석 → 실패 원인 분석 → 수정 제안 → 리포트**까지의 검증 흐름을 자동으로 수행하는 것을 목표로 합니다. "AI가 Verilog 코드를 써준다"가 아니라 **"AI가 RTL 검증 과정을 자동화한다"**는 방향으로 설계했습니다.

시뮬레이터는 **Vivado 2024.2 (xsim)** 를 사용하며, 이후 SystemVerilog / UVM 확장을 고려해 시뮬레이터 부분을 어댑터로 분리했습니다.

> 상태 표기: ✅ 구현·검증 완료 · 🚧 진행 중 · 📝 예정

## 📁 Folder Description

| 폴더 | 역할 | 상태 |
|---|---|---|
| `core/` | 공통 데이터 모델(`StepResult`, `RunResult`, `SimResult`, `ErrorItem`)과 로그 파서 | 🚧 |
| `sim/` | 시뮬레이터 실행 계층. `Simulator` 추상 클래스, `XsimSim` 어댑터, 도구 실행기(`run_tool`), 작업 폴더 생성, Tcl 템플릿 | ✅ |
| `scripts/` | 터미널에서 한 번 실행해 결과를 확인하는 CLI (`run_once.py`) | ✅ |
| `tests/` | 단위·통합 테스트, 그리고 파서 테스트용 실제 xsim 로그·VCD 샘플(`tests/data/`) | ✅ |
| `Manual_test/` | 자동화 전에 `xvlog → xelab → xsim` 흐름을 손으로 검증한 기록 (첫 대상 DUT: async FIFO) | ✅ |
| `runs/` | 실행마다 생성되는 고유 작업 폴더 (Git 추적 제외) | ✅ |
| `agent/` | LLM 기반 TB Generator, Debug Agent Loop (Tool Use) | 📝 |
| `dut/` | 검증 대상 RTL 모음 (UART, SPI, FIFO, I2C) | 📝 |
| `bugs/` | 의도적으로 버그를 주입한 DUT와 정답 메타데이터 (평가용) | 📝 |
| `reports/` | 회귀 실행 결과 리포트 | 📝 |

## 📂 Directory Structure

```text
Agent/
├── core/
│   ├── models.py               # StepResult, RunResult, SimResult, ErrorItem
│   └── log_parser.py           # xvlog / xelab / xsim 로그 파서 (진행 중)
├── sim/
│   ├── base.py                 # Simulator 추상 클래스
│   ├── runner.py               # run_tool(): 도구 한 단계 실행 (타임아웃, 프로세스 트리 종료)
│   ├── xsim.py                 # XsimSim: xvlog → xelab → xsim 조율
│   ├── workdir.py              # 실행마다 고유한 작업 폴더 경로 생성
│   └── templates/
│       └── run.tcl.tmpl        # VCD 덤프용 Tcl 템플릿
├── scripts/
│   └── run_once.py             # 한 번 실행하고 단계별 결과 요약 출력
├── tests/
│   ├── data/                   # 실제 xsim 로그, VCD 샘플
│   ├── test_models.py
│   ├── test_runner.py
│   ├── test_xsim_adapter.py
│   └── test_log_parser.py
├── Manual_test/                # Phase 0: 수동 실행 검증
│   ├── dut/                    # async FIFO RTL
│   ├── tb/                     # 기준 Testbench
│   ├── runs/manual/            # files.f, run.tcl
│   └── NOTES.md
├── runs/                       # 실행별 작업 폴더 (Git 무시)
├── NOTES_phase1.md             # Phase 1 개발 기록
├── pytest.ini
├── requirements.txt
└── README.md
```

예정된 구조 (📝):

```text
Agent/
├── agent/
│   ├── orchestrator.py         # 파이프라인 제어
│   ├── debug_agent.py          # Debug Agent Loop (Tool Use)
│   ├── tools.py                # LLM에 노출할 Tool 정의
│   └── prompts/                # TB 생성, 디버깅 프롬프트
├── core/
│   ├── analyzer.py             # RTL Analyzer
│   ├── tb_generator.py
│   ├── vcd_reader.py           # 시뮬레이터 무관 VCD 조회
│   └── report.py
├── dut/                        # uart, spi, fifo, i2c
├── bugs/                       # 버그 주입본 + 정답 메타데이터
└── reports/
```

## ⚙️ How the Agent Works

### 전체 흐름

```text
[RTL 파일]
   ↓
[1. RTL Analyzer]      포트/파라미터/FSM 추출 (LLM + 정규식)                      📝
   ↓
[2. TB Generator]      LLM이 self-checking TB 생성                               📝
   │                   (TB는 [TB] PASS / [TB] FAIL 출력 규약 강제)
   ↓
[2.5 Compile Gate]     xvlog 문법 검사 (결정적)                                  📝
   │                   실패 시 에러 메시지와 함께 2번으로 되돌려 재시도 (최대 N회)
   ↓
[3. Simulator Tool]    xvlog → xelab → xsim -tclbatch run.tcl                    ✅
   │                   → sim.log, dump.vcd  (결정적)
   │                   ※ Simulator 추상 클래스 + XsimSim 어댑터로 격리
   ↓
[4. Log Analyzer]      xsim 로그 파싱 → 공통 SimResult로 변환 (결정적)            🚧
   │                   PASS/FAIL, 에러 라인, ERROR/FATAL_ERROR, 타임아웃 판정
   ↓ FAIL일 때만
[5. Debug Agent Loop]  ← 핵심 Agent 구간 (LLM + Tool Use, 최대 반복 제한)         📝
     ├ get_log_snippet   로그 일부 조회
     ├ list_signals      계층/신호 목록 조회
     ├ read_vcd_signal   VCD에서 신호·시간 구간만 조회
     ├ read_rtl          RTL 해당 구간 읽기
     ├ 원인 가설 → 검증
     ├ propose_fix       수정 제안(diff), ★적용은 사람 승인 후★
     └ rerun_sim         runs/ 복사본에서만 재시뮬
   ↓
[6. Regression / Report]  결과 누적, Markdown 리포트                              📝
                          컴파일 성공률 / 버그 탐지율 / 원인 위치 정확도 / 평균 반복 횟수 등
```

## 🗺️ Development Status

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | `xvlog → xelab → xsim` 수동 실행, Tcl로 VCD 생성 검증 (`Manual_test/NOTES.md`) | ✅ |
| 1 | `XsimSim` 어댑터: 격리 실행, 중단 정책, 타임아웃과 프로세스 트리 종료 (`NOTES_phase1.md`) | ✅ |
| 2 | 로그 파서와 `SimResult` 판정 | 🚧 |
| 3 | VCD Reader (신호 alias 처리, 구간 조회) | 📝 |
| 4 | 버그 주입 세트와 평가 하네스 | 📝 |
| 5 | RTL Analyzer | 📝 |
| 6 | TB Generator + Compile Gate | 📝 |
| 7 | Debug Agent Loop | 📝 |
| 8 | Regression / Report, UART·SPI·I2C로 확장 | 📝 |

이후 SystemVerilog / UVM 기반 검증으로 확장할 계획입니다.
