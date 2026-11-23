# RTL Verification AI Agent
RTL 검증 업무를 자동화하는 AI Agent 프로젝트입니다.

RTL을 입력하면 **Testbench 생성 → 시뮬레이션 → 로그 분석 → 실패 원인 분석 → 수정 제안 → 리포트**까지의 검증 흐름을 자동으로 수행하는 것을 목표로 합니다. "AI가 Verilog 코드를 써준다"가 아니라 **"AI가 RTL 검증 과정을 자동화한다"**는 방향으로 설계했습니다.

시뮬레이터는 **Vivado 2024.2 (xsim)** 를 사용하며, 이후 SystemVerilog / UVM 확장을 고려해 시뮬레이터 부분을 어댑터로 분리했습니다.

> 상태 표기: ✅ 구현·검증 완료 · 🚧 진행 중 · 📝 예정

## 📁 Folder Description

| 폴더 | 역할 | 상태 |
|---|---|---|
| `core/` | 데이터 모델(`StepResult`, `RunResult`, `ErrorItem`, `SimResult`), 로그 파서, 판정(`analyze`), VCD 읽기(`VcdReader`)와 Agent용 VCD 도구(`VcdTools`), 버그 주입(`bugs.py`), 평가 하네스(`evaluator.py`), 평가 리포트(`eval_report.py`), RTL Analyzer(`rtl_analyzer.py`, `rtl_clkrst.py`, `rtl_summary.py`) | ✅ |
| `sim/` | 시뮬레이터 실행 계층. `Simulator` 추상 클래스, `XsimSim` 어댑터, 도구 실행기(`run_tool`), 작업 폴더 생성, Tcl 템플릿 | ✅ |
| `scripts/` | 터미널 CLI (`run_once.py`: 실행 + 판정 출력, `run_eval.py`: 평가 실행, `make_baseline_report.py`: 리포트 생성, `show_rtl.py`: RTL 분석 결과 표, `make_rtl_summary.py`: TB Generator 입력 요약)와 로그 샘플 수집 도구 | ✅ |
| `tests/` | 단위·통합 테스트 183개, 그리고 테스트용 실제 xsim 로그·VCD 샘플(`tests/data/`) | ✅ |
| `docs/` | 단계별 개발 기록 (`NOTES_p0.md` ~ `NOTES_ps5.md`) | ✅ |
| `Manual_test/` | 자동화 전에 `xvlog → xelab → xsim` 흐름을 손으로 검증한 기록 (첫 대상 DUT: async FIFO) | ✅ |
| `runs/` | 실행마다 생성되는 고유 작업 폴더 (Git 추적 제외) | ✅ |
| `agent/` | LLM 기반 TB Generator, Debug Agent Loop (Tool Use) | 📝 |
| `dut/` | 평가용 골든 DUT. 지금은 `sync_fifo`(골든 RTL + self-checking TB), UART/SPI/I2C 추가 예정 | ✅ |
| `bugs/` | 버그 카탈로그와 정답 메타데이터 (`sync_fifo`: 버그 17 + 동등 변형 2) | ✅ |
| `reports/` | 평가 리포트 (`baseline_sync_fifo.md`). 회귀 리포트는 📝 | 🚧 |

## 📂 Directory Structure

```text
Agent/
├── core/
│   ├── models.py               # StepResult, RunResult, ErrorItem, SimResult
│   ├── log_parser.py           # xvlog / xelab / xsim 로그 파서, time_to_ps
│   ├── analyzer.py             # analyze(RunResult) -> SimResult 판정
│   ├── vcd_reader.py           # 시뮬레이터 무관 VCD 조회 (ID 기준 이력, 에지 샘플링, net 후보)
│   ├── vcd_tools.py            # Agent(LLM)용 VCD 도구 (출력 상한, 오류를 dict로 반환)
│   ├── bugs.py                 # 버그 카탈로그 로드, 패치 적용 (줄 번호와 diff를 정답으로 반환)
│   ├── evaluator.py            # 골든/변형 일괄 실행, detected/survived/invalid 분류, 집계
│   ├── eval_report.py          # results.json -> Markdown 리포트
│   ├── rtl_analyzer.py         # RTL Analyzer: 모듈/포트/파라미터/인스턴스, 계층, top 추정, top 인터페이스
│   ├── rtl_clkrst.py           # always 블록 기반 클럭/리셋 판별 (근거 evidence 포함)
│   └── rtl_summary.py          # TB Generator용 요약 dict 생성과 스키마 검증
├── sim/
│   ├── base.py                 # Simulator 추상 클래스
│   ├── runner.py               # run_tool(): 도구 한 단계 실행 (타임아웃, 프로세스 트리 종료)
│   ├── xsim.py                 # XsimSim: xvlog → xelab → xsim 조율
│   ├── workdir.py              # 실행마다 고유한 작업 폴더 경로 생성
│   └── templates/
│       └── run.tcl.tmpl        # VCD 덤프용 Tcl 템플릿
├── scripts/
│   ├── run_once.py             # 한 번 실행하고 단계별 결과와 판정 출력
│   ├── collect_xsim_samples.py # TB 변형 6종으로 xsim 로그 샘플 수집
│   ├── run_eval.py             # 골든 + 버그 변형 전체 평가 실행
│   ├── make_baseline_report.py # 평가 결과로 baseline 리포트 생성
│   ├── show_rtl.py             # RTL 분석 결과(모듈, 계층, 클럭/리셋) 출력
│   └── make_rtl_summary.py     # TB Generator 입력용 요약 JSON 생성
├── tests/
│   ├── data/                   # 실제 xsim 로그, VCD 샘플 (README 참고)
│   ├── test_models.py          #  6
│   ├── test_runner.py          #  6
│   ├── test_xsim_adapter.py    #  7
│   ├── test_log_parser.py      # 13
│   ├── test_analyzer.py        # 13
│   ├── test_pipeline.py        #  2  (실제 Vivado 실행 → 판정)
│   ├── test_vcd_reader.py      # 21
│   ├── test_vcd_tools.py       # 10
│   ├── test_golden_sync_fifo.py #  2  (골든 PASS, 단순 변형 FAIL: 실제 Vivado)
│   ├── test_bugs.py            #  9
│   ├── test_evaluator.py       #  7
│   ├── test_eval_report.py     #  2
│   ├── test_rtl_analyzer.py    # 24
│   ├── test_rtl_hierarchy.py   # 18
│   ├── test_rtl_clkrst.py      # 21
│   └── test_rtl_summary.py     # 22
├── docs/
│   ├── NOTES_p0.md             # Phase 0: 수동 실행
│   ├── NOTES_ps1.md            # Phase 1: XsimSim 어댑터
│   ├── NOTES_ps2.md            # Phase 2: 로그 파서와 판정
│   ├── NOTES_ps3.md            # Phase 3: VCD Reader와 Agent용 도구
│   ├── NOTES_ps4.md            # Phase 4: 골든 DUT, 버그 주입, 평가 하네스
│   └── NOTES_ps5.md            # Phase 5: RTL Analyzer
├── dut/
│   └── sync_fifo/
│       ├── rtl/                # 골든 RTL (원본 그대로)
│       └── tb/                 # tb_sync_fifo_sc.v (self-checking), tb_sync_fifo_ref.v (원본 TB)
├── bugs/
│   └── sync_fifo/
│       └── bugs.json           # 버그 카탈로그 19개
├── reports/
│   └── baseline_sync_fifo.md   # TB-only 평가 기준선 (make_baseline_report로 생성)
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
│   ├── tb_generator.py
│   └── report.py
├── dut/                        # uart, spi, i2c 추가 예정
└── bugs/                       # 위 DUT용 카탈로그 추가 예정
```

## ⚙️ How the Agent Works

### 전체 흐름

```text
[RTL 파일]
   ↓
[1. RTL Analyzer]      포트/파라미터/계층/클럭·리셋/timescale 추출 (결정적, LLM 없음) ✅
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

### VCD Reader / VCD Tools (✅)

`VcdReader`는 시뮬레이터와 무관하게 VCD를 읽고, `VcdTools`는 그 위에 LLM용 도구 3개를 얹습니다.

| 구분 | 내용 |
|---|---|
| ID 기준 저장 | 같은 VCD ID를 여러 계층 이름이 공유(alias)하므로 이력을 이름이 아니라 ID로 저장합니다. |
| 값 의미 | VCD는 값이 바뀔 때만 기록하므로 `value_at(t)`는 t 이하의 마지막 변화값입니다. `end_time_ps`는 마지막 타임스탬프이고 시뮬 종료 시각이 아닙니다. |
| 에지 샘플링 | `sample_on_edge`는 기본적으로 에지 **직전** 값(플립플롭이 읽는 값)을 반환합니다. |
| net 후보 | `net_group`은 확실한 alias와 "이력이 같은 후보"를 구분해서 반환합니다. 후보는 같은 net의 증명이 아닙니다. |
| 조회 상태 | `status`가 `not_in_vcd`(예: `mem` 배열), `not_loaded`, `no_changes`, `always_x`, `ok`를 알려 줍니다. |
| 큰 파일 | 줄 단위 스트리밍 파싱, 신호/시간 구간 적재 필터. 143MB는 약 8.5초에 메모리 1.1GB (합성 데이터 기준) |
| LLM 도구 | `list_signals` / `read_vcd_signal` / `sample_signals`. 출력 상한, `truncated`와 `next_t0_ps`, 오류는 dict로 반환 |

### Debug Agent Loop (📝)

FAIL일 때만 동작하는 Agent 구간입니다. LLM이 도구를 골라 쓰며 **가설 → 증거 수집 → 가설 수정**을 반복하고, 구조화된 결론(`final_report`)으로 종료합니다.

| Tool | 역할 |
|---|---|
| `get_log_snippet` | 로그의 특정 구간만 조회 (전체 로그를 LLM에 넣지 않음) |
| `list_signals` | VCD의 계층·신호 목록 조회 (✅ `VcdTools`) |
| `read_vcd_signal` | 신호·시간 구간만 조회. alias와 같은 이력 후보를 함께 반환 (✅ `VcdTools`) |
| `sample_signals` | 클럭 에지마다 여러 신호 샘플링 (✅ `VcdTools`) |
| `read_rtl` | RTL의 특정 줄 범위 조회 |
| `propose_fix` | 수정안을 diff로 저장만 함 (자동 적용 안 함) |
| `rerun_sim` | `runs/` 복사본에서만 재시뮬레이션 |

가드레일: 최대 반복 횟수 제한, 원본 파일 쓰기 금지, 도구 출력 길이 제한, TB/RTL 수정 권한 분리.

### 평가 하네스 (✅ TB-only 기준선 / 📝 Agent 평가)

DUT별로 버그를 주입한 변형(`bugs/`)과 정답 메타데이터(파일, 줄, 유형)를 만들어 다음 지표를 측정합니다. 변형 RTL은 파일로 저장하지 않고 카탈로그의 패치를 골든 RTL에 적용해서 만듭니다. 패치 대상이 바뀌면 즉시 에러가 나므로 정답지가 골든과 어긋나지 않습니다.

**실행 규칙**

| 대상 | 결과 | 분류 |
|---|---|---|
| 골든 | PASS가 아님 | 평가 중단 (기준선이 깨짐) |
| 일반 변형 | FAIL | `detected` |
| 일반 변형 | PASS, NO_VERDICT | `survived` (TB가 못 잡음) |
| 일반 변형 | COMPILE/ELAB_ERROR, TIMEOUT | `invalid` (점수 제외, 경고) |
| 동등 변형 | 생존 | `equivalent_ok` (top 기준으로 관측 불가능한 변형, 점수 제외) |

**TB-only 기준선 (sync FIFO, 실제 Vivado)**: 골든 PASS, 실제 버그 17개를 모두 `detected`, 동등 변형 2개는 `equivalent_ok`, **mutation score 100%**, 첫 불일치 시각 27~417 ns, 전체 221초. 변형이 한 줄 치환 단일 버그뿐이라 TB가 완전하다는 뜻은 아니며, 이 기준선은 이후 TB Generator와 Debug Agent 결과와 비교하는 용도입니다 (`docs/NOTES_ps4.md`).

| 지표 | 의미 |
|---|---|
| 컴파일 성공률 | LLM이 생성한 TB가 재시도 횟수 내에 컴파일되는 비율 |
| 골든 PASS율 | 정상 DUT에서 생성된 TB가 PASS하는 비율 (TB 자체의 오류 검출) |
| 버그 탐지율 (mutation score) | 주입한 버그를 FAIL로 잡아내는 비율. TB-only 기준선은 측정 완료 (100%), LLM이 만든 TB는 Phase 6 |
| 원인 위치 정확도 | Agent가 지목한 파일·줄·신호가 정답과 일치하는 비율 |
| 평균 반복 횟수 | 원인 분석까지 걸린 Agent 루프 횟수 |

## 🧪 Verification of the Tooling

| 구분 | 내용 |
|---|---|
| 자동 테스트 | 183개 (`pytest -q`). Vivado가 없으면 실제 실행 테스트 5개, 샘플 VCD가 없으면 샘플 기반 테스트 3개는 건너뜀 |
| 실제 Vivado 실행 | 정상 / PASS / FAIL / `$error` / `$fatal` / PASS+에러 / 타임아웃 / 컴파일 에러 8종을 실제로 돌려 판정이 모두 기대와 일치 |
| 평가 하네스 | 골든 1 + 버그 변형 19개를 실제 Vivado로 실행 (221초). 판정 규칙은 가짜 Runner로 Vivado 없이 테스트 |
| RTL Analyzer | sync FIFO(모듈 3개)와 async FIFO(모듈 5개)의 포트 폭, 계층, 클럭/리셋, timescale을 실제 소스에서 추출해 정답과 대조. 요약은 스키마 검증과 TB 생성 차단 조건(`blockers`)을 테스트로 고정 |
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

```powershell
# 평가: 골든 + 버그 변형 전체 (약 4분), 결과는 runs/eval_<시각>/results.json
python -m scripts.run_eval
python -m scripts.run_eval --only B07 B17        # 일부만

# 리포트 생성 -> reports/baseline_sync_fifo.md
python -m scripts.make_baseline_report

# RTL 분석: 모듈/포트/계층/클럭/리셋 표, TB Generator 입력용 JSON 요약
python -m scripts.show_rtl dut/sync_fifo/rtl
python -m scripts.make_rtl_summary Manual_test/dut
```

## 🗺️ Development Status

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | `xvlog → xelab → xsim` 수동 실행, Tcl로 VCD 생성 검증 (`docs/NOTES_p0.md`) | ✅ |
| 1 | `XsimSim` 어댑터: 격리 실행, 중단 정책, 타임아웃과 프로세스 트리 종료 (`docs/NOTES_ps1.md`) | ✅ |
| 2 | 로그 파서와 `SimResult` 판정 (`docs/NOTES_ps2.md`) | ✅ |
| 3 | VCD Reader (ID 기준 이력, alias, 에지 샘플링, net 후보)와 Agent용 도구 (`docs/NOTES_ps3.md`) | ✅ |
| 4 | 골든 DUT(sync FIFO)와 self-checking TB, 버그 주입 세트, 평가 하네스와 TB-only 기준선 (`docs/NOTES_ps4.md`) | ✅ |
| 5 | RTL Analyzer: 모듈/포트/파라미터/계층/top 추정, 클럭·리셋 판별, timescale 상태, TB Generator용 요약 JSON과 검증 (`docs/NOTES_ps5.md`) | ✅ |
| 6 | TB Generator + Compile Gate | 🚧 |
| 7 | Debug Agent Loop | 📝 |
| 8 | Regression / Report, UART·SPI·I2C로 확장 | 📝 |

### 버전 로드맵

위 Phase는 **v1**을 만드는 단계이고, 이후는 버전 단위로 확장합니다. 각 버전은 그 자체로 완성품이 되도록 범위를 나눕니다.

| 버전 | 범위 | 완료 기준 (측정 지표) |
|---|---|---|
| RVA v1 | Verilog RTL 기능 검증 자동화 (Phase 0~8) | 평가 세트에서 골든 PASS율, mutation score, 원인 위치 정확도 측정 |
| RVA v1.5 | v1 최적화 (프롬프트, 재시도 정책, 비용과 시간 절감) | v1과 같은 지표가 개선됨을 수치로 확인 |
| RVA v2 | SystemVerilog + UVM (SVA, 커버리지, 제약 랜덤, UVM 환경 생성) | 같은 DUT에서 v1 대비 검출력과 커버리지 비교 |
| RVA v2.5 | v2 최적화 | v2와 같은 지표 개선 확인 |
| RVA v3 | PPA 분석 (합성 리포트 파싱: timing, power, area 요약. 수치는 파서, LLM은 요약만) | 합성 리포트에서 추출한 값과 원본의 일치 검증 |

버전 사이의 최적화는 "막연한 개선"이 아니라 위 지표의 목표값을 먼저 정하고 달성 여부로 마무리합니다.

이후 SystemVerilog / UVM 기반 검증으로 확장할 계획입니다.