# RTL Verification AI Agent
RTL 검증 업무를 자동화하는 AI Agent 프로젝트입니다.

RTL을 입력하면 **Testbench 생성 → 시뮬레이션 → 로그 분석 → 실패 원인 분석 → 수정 제안 → 리포트**까지의 검증 흐름을 자동으로 수행하는 것을 목표로 합니다. "AI가 Verilog 코드를 써준다"가 아니라 **"AI가 RTL 검증 과정을 자동화한다"**는 방향으로 설계했습니다.

시뮬레이터는 **Vivado 2024.2 (xsim)** 를 사용하며, 이후 SystemVerilog / UVM 확장을 고려해 시뮬레이터 부분을 어댑터로 분리했습니다.

> 상태 표기: ✅ 구현·검증 완료 · 🚧 진행 중 · 📝 예정

## 📁 Folder Description

| 폴더 | 역할 | 상태 |
|---|---|---|
| `core/` | 데이터 모델(`StepResult`, `RunResult`, `ErrorItem`, `SimResult`), 로그 파서, 판정(`analyze`) | ✅ |
| `sim/` | 시뮬레이터 실행 계층. `Simulator` 추상 클래스, `XsimSim` 어댑터, 도구 실행기(`run_tool`), 작업 폴더 생성, Tcl 템플릿 | ✅ |
| `scripts/` | 터미널 CLI (`run_once.py`: 실행 + 판정 출력)와 로그 샘플 수집 도구 | ✅ |
| `tests/` | 단위·통합 테스트 47개, 그리고 테스트용 실제 xsim 로그·VCD 샘플(`tests/data/`) | ✅ |
| `docs/` | 단계별 개발 기록 (`NOTES_p0.md`, `NOTES_ps1.md`, `NOTES_ps2.md`) | ✅ |
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
│   ├── models.py               # StepResult, RunResult, ErrorItem, SimResult
│   ├── log_parser.py           # xvlog / xelab / xsim 로그 파서, time_to_ps
│   └── analyzer.py             # analyze(RunResult) -> SimResult 판정
├── sim/
│   ├── base.py                 # Simulator 추상 클래스
│   ├── runner.py               # run_tool(): 도구 한 단계 실행 (타임아웃, 프로세스 트리 종료)
│   ├── xsim.py                 # XsimSim: xvlog → xelab → xsim 조율
│   ├── workdir.py              # 실행마다 고유한 작업 폴더 경로 생성
│   └── templates/
│       └── run.tcl.tmpl        # VCD 덤프용 Tcl 템플릿
├── scripts/
│   ├── run_once.py             # 한 번 실행하고 단계별 결과와 판정 출력
│   └── collect_xsim_samples.py # TB 변형 6종으로 xsim 로그 샘플 수집
├── tests/
│   ├── data/                   # 실제 xsim 로그, VCD 샘플 (README 참고)
│   ├── test_models.py          #  6
│   ├── test_runner.py          #  6
│   ├── test_xsim_adapter.py    #  7
│   ├── test_log_parser.py      # 13
│   ├── test_analyzer.py        # 13
│   └── test_pipeline.py        #  2  (실제 Vivado 실행 → 판정)
├── docs/
│   ├── NOTES_p0.md             # Phase 0: 수동 실행
│   ├── NOTES_ps1.md            # Phase 1: XsimSim 어댑터
│   └── NOTES_ps2.md            # Phase 2: 로그 파서와 판정
├── Manual_test/                # Phase 0: 수동 실행 검증
│   ├── dut/                    # async FIFO RTL
│   ├── tb/                     # 기준 Testbench
│   └── runs/manual/            # files.f, run.tcl
├── runs/                       # 실행별 작업 폴더 (Git 무시)
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
│   ├── vcd_reader.py           # 시뮬레이터 무관 VCD 조회 (Phase 3)
│   ├── analyzer_rtl.py         # RTL Analyzer
│   ├── tb_generator.py
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
   │                   → 단계별 로그, dump.vcd  (결정적)
   │                   ※ Simulator 추상 클래스 + XsimSim 어댑터로 격리
   ↓
[4. Log Analyzer]      로그 파싱 → 공통 SimResult로 변환 (결정적)                  ✅
   │                   PASS/FAIL/NO_VERDICT, 에러 목록, 미분석 파일, 타임아웃 판정
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

### 설계 원칙

| 원칙 | 내용 |
|---|---|
| 결정적 구간과 LLM 구간의 분리 | 컴파일, 시뮬레이션, 로그 파싱, 판정, VCD 조회는 LLM 없이 동작합니다. LLM은 TB 생성, 원인 추론, 수정 제안에만 사용합니다. 실패했을 때 TB 문제인지 도구 문제인지 Agent 문제인지 구분할 수 있습니다. |
| 사실과 해석의 분리 | 실행부는 종료 코드·출력·시간 같은 **원본 사실**(`RunResult`)만 만들고, 판정은 별도 계층이 **`SimResult`**로 해석합니다. 파서 규칙을 바꿔도 실행부는 영향받지 않습니다. |
| 시뮬레이터 격리 | Agent는 `Simulator` 인터페이스만 호출합니다. xsim의 명령, Tcl, 로그 위치는 `XsimSim` 안에 가둬서 SystemVerilog / UVM 확장 시 어댑터와 프롬프트만 교체합니다. |
| 격리 실행 | 실행마다 고유한 작업 폴더를 만들고, 이미 존재하면 에러를 냅니다. 이전 컴파일 결과(`xsim.dir`) 재사용으로 에러가 가려지는 문제를 막습니다. 원본 RTL/TB는 읽기 전용입니다. |
| 로그로 판정 | **`xsim`의 종료 코드는 `$error`/`$fatal`이 있어도 0**입니다(실측). 시뮬레이션 FAIL은 종료 코드가 아니라 로그로 판정합니다. |
| 사람의 승인 | Agent는 수정안을 **diff로 제안만** 하고, 적용은 사람이 승인한 뒤에 합니다. RTL 수정 권한과 TB 수정 권한을 분리해서 "테스트를 고쳐서 통과시키는" 행동을 차단합니다. |
| 평가 가능성 | 정답을 아는 버그를 주입한 DUT로 컴파일 성공률, 버그 탐지율, 원인 위치 정확도를 수치로 측정합니다. |

### Simulator Tool (✅)

`XsimSim.run(files, top, workdir)`가 한 번의 실행을 수행합니다.

```text
1. 소스 파일 검증 → 고유 workdir 생성
2. files.f(절대경로), run.tcl(템플릿) 생성
3. xvlog -sv -f files.f
   xelab -debug typical <top> -s snap
   xsim snap -tclbatch run.tcl -log sim.log
4. 각 단계의 종료 코드·출력·시간을 StepResult로 기록
   - xvlog / xelab이 실패하거나 타임아웃이면 다음 단계를 실행하지 않고 중단
5. dump.vcd가 생성되었으면 경로를 RunResult에 기록
```

| 항목 | 내용 |
|---|---|
| 타임아웃 | 단계별로 설정(기본 `xvlog` 60초 / `xelab` 120초 / `xsim` 60초). 초과하면 `taskkill /T /F`로 **프로세스 트리 전체**를 종료해 시뮬레이터가 남지 않게 함 |
| VCD 생성 | TB에 `$dumpfile`을 넣지 않고 Tcl(`open_vcd`, `log_vcd`)로 생성. 기존 TB를 수정할 필요가 없음 |
| 출력 수집 | stdout과 stderr를 합쳐 터미널에서 본 순서 그대로 보존 |

### Log Analyzer (✅)

`analyze(RunResult)`가 파서 3개(`xvlog`, `xelab`, `xsim`)의 결과를 모아 아래 상태 중 하나로 판정합니다. 위에서 아래로 처음 해당하는 것이 적용됩니다.

| 순서 | 상태 | 조건 |
|---|---|---|
| 1 | `TIMEOUT` | 어느 단계든 타임아웃 |
| 2 | `COMPILE_ERROR` | `xvlog` 종료 코드 ≠ 0 또는 `ERROR` 있음 |
| 3 | `ELAB_ERROR` | `xelab` 종료 코드 ≠ 0, `ERROR` 있음, 또는 스냅샷 미생성 |
| 4 | `FAIL` | `xsim`에 `Error:`/`Fatal:`이 있거나 `[TB] FAIL`이 있음 (종료 코드가 0이어도) |
| 5 | `PASS` | `[TB] PASS`가 있고 위에 해당 없음 |
| 6 | `NO_VERDICT` | 끝까지 실행됐지만 PASS/FAIL 마커가 없음 |

- **PASS는 명시적인 `[TB] PASS` 마커가 있을 때만** 인정합니다. TB가 PASS를 출력해도 시뮬레이터 에러가 있으면 FAIL이며, 이때 `tb_verdict`(TB가 한 말)와 `status`(종합 판정)가 달라집니다.
- 에러는 `ERROR: [<도구> <코드>] <메시지> [<파일>:<줄>]`과 시뮬레이터의 `Error:`/`Fatal:` 두 줄 형식을 모두 `ErrorItem`으로 추출하고, **첫 에러만 주 원인**으로 표시합니다 (나머지는 연쇄 에러).
- 요청한 파일과 `xvlog`가 분석을 시작한 파일을 비교해, 에러 뒤에서 분석되지 못한 파일을 `unanalyzed_files`로 알려 줍니다.
- 시뮬레이션 종료 시각은 VCD가 아니라 로그의 `$finish called at time` 줄에서 가져옵니다.

실행 예시 (`run_once`):

```text
status    : COMPILE_ERROR (stage: xvlog)
unanalyzed:
  - .../dut/synchronizer.v
  - .../tb/tb_async_fifo.v
errors    :  (* = 주 원인)
  * [xvlog] ERROR VRFC 10-4982: syntax error near 'end' (.../fifo_mem_err1.v:21)
    [xvlog] ERROR VRFC 10-8549: SystemVerilog keyword 'end' used in incorrect context (...:21)
    [xvlog] ERROR VRFC 10-8530: module 'fifo_mem' is ignored due to previous errors (...:3)
```

### Debug Agent Loop (📝)

FAIL일 때만 동작하는 Agent 구간입니다. LLM이 도구를 골라 쓰며 **가설 → 증거 수집 → 가설 수정**을 반복하고, 구조화된 결론(`final_report`)으로 종료합니다.

| Tool | 역할 |
|---|---|
| `get_log_snippet` | 로그의 특정 구간만 조회 (전체 로그를 LLM에 넣지 않음) |
| `list_signals` | VCD의 계층·신호 목록 조회 |
| `read_vcd_signal` | 신호·시간 구간만 조회. 같은 ID를 공유하는 alias 후보를 함께 반환 |
| `read_rtl` | RTL의 특정 줄 범위 조회 |
| `propose_fix` | 수정안을 diff로 저장만 함 (자동 적용 안 함) |
| `rerun_sim` | `runs/` 복사본에서만 재시뮬레이션 |

가드레일: 최대 반복 횟수 제한, 원본 파일 쓰기 금지, 도구 출력 길이 제한, TB/RTL 수정 권한 분리.

### 평가 (📝)

DUT별로 버그를 주입한 변형본(`bugs/`)과 정답 메타데이터(위치, 유형)를 만들고 다음 지표를 측정합니다.

| 지표 | 의미 |
|---|---|
| 컴파일 성공률 | LLM이 생성한 TB가 재시도 횟수 내에 컴파일되는 비율 |
| 골든 PASS율 | 정상 DUT에서 생성된 TB가 PASS하는 비율 (TB 자체의 오류 검출) |
| 버그 탐지율 | 주입한 버그를 FAIL로 잡아내는 비율 |
| 원인 위치 정확도 | Agent가 지목한 파일·줄·신호가 정답과 일치하는 비율 |
| 평균 반복 횟수 | 원인 분석까지 걸린 Agent 루프 횟수 |

## 🧪 Verification of the Tooling

| 구분 | 내용 |
|---|---|
| 자동 테스트 | 47개 (`pytest -q`). Vivado가 없으면 실제 실행 테스트 3개는 건너뜀 |
| 실제 Vivado 실행 | 정상 / PASS / FAIL / `$error` / `$fatal` / PASS+에러 / 타임아웃 / 컴파일 에러 8종을 실제로 돌려 판정이 모두 기대와 일치 |
| 샘플 데이터 | 손으로 쓴 로그가 아니라 실제 xsim 출력 (`tests/data/README.md`) |

## 🚀 Quick Start

```powershell
# 환경 (Windows / PowerShell, Python 3.10 이상, Vivado 2024.2가 PATH에 등록되어 있어야 함)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 테스트
pytest -q

# 한 번 실행 (실행 + 판정 출력)
python -m scripts.run_once --top async_fifo_tb --label fifo `
  --files Manual_test/dut/async_fifo.v Manual_test/dut/bin2gray.v Manual_test/dut/fifo_ctrl.v `
          Manual_test/dut/fifo_mem.v Manual_test/dut/synchronizer.v Manual_test/tb/tb_async_fifo.v
```

실행 결과는 `runs/<시각>_<label>_<id>/` 아래에 `files.f`, `run.tcl`, 각 도구의 로그, `dump.vcd`로 생성됩니다.

## 🗺️ Development Status

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | `xvlog → xelab → xsim` 수동 실행, Tcl로 VCD 생성 검증 (`docs/NOTES_p0.md`) | ✅ |
| 1 | `XsimSim` 어댑터: 격리 실행, 중단 정책, 타임아웃과 프로세스 트리 종료 (`docs/NOTES_ps1.md`) | ✅ |
| 2 | 로그 파서와 `SimResult` 판정 (`docs/NOTES_ps2.md`) | ✅ |
| 3 | VCD Reader (ID 기준 이력, alias 처리, 구간 조회) | 🚧 |
| 4 | 버그 주입 세트와 평가 하네스 | 📝 |
| 5 | RTL Analyzer | 📝 |
| 6 | TB Generator + Compile Gate | 📝 |
| 7 | Debug Agent Loop | 📝 |
| 8 | Regression / Report, UART·SPI·I2C로 확장 | 📝 |

이후 SystemVerilog / UVM 기반 검증으로 확장할 계획입니다.
