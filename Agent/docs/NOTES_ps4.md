# Phase 4 NOTES: 골든 DUT, 버그 주입 세트, 평가 하네스

> RTL Verification AI Agent 개발의 Phase 4 기록.
> 목적: 정답을 아는 버그를 심은 DUT 세트와 평가 하네스를 만들고, **LLM 없이 결정적 구간만으로** TB가 버그를 얼마나 잡는지 기준선을 잰다.
> 이후 TB Generator(Phase 6)와 Debug Agent(Phase 7)는 같은 변형 세트와 정답 메타데이터로 평가한다.
> 작성 기준일: 2026-11-22 / 골든 DUT: sync FIFO

상태 표기: ✅ 확인됨 · ⚠️ 부분 확인/추정 · ❓ 미확인(가설) · ⏸ 보류

---

## 1. 구조

```
dut/sync_fifo/rtl (골든)  ──apply_bug──▶ 변형 RTL ┐
bugs/sync_fifo/bugs.json (정답지)                 ├─▶ XsimSim → analyze → Judged
dut/sync_fifo/tb (self-checking TB) ──────────────┘          │
                                                             ▼
                             evaluate() → results.json → baseline 리포트
```

| 파일 | 역할 |
|---|---|
| `dut/sync_fifo/rtl/` | 골든 RTL 3개 (`sync_fifo.v`, `fifo_ctrl.v`, `fifo_mem.v`). 원본 그대로 |
| `dut/sync_fifo/tb/tb_sync_fifo_sc.v` | self-checking TB (top: `sync_fifo_sc_tb`), 평가에 사용 |
| `dut/sync_fifo/tb/tb_sync_fifo_ref.v` | 원래 TB. 파형 확인용이고 self-checking 아님 |
| `bugs/sync_fifo/bugs.json` | 버그 카탈로그 19개 (실제 버그 17 + 동등 변형 2) |
| `core/bugs.py` | `load_catalog()`, `apply_bug()` |
| `core/evaluator.py` | `evaluate()`, `classify()`, `summarize()`, CHECK_FAIL 파서, `xsim_runner()` |
| `core/eval_report.py` | results.json → Markdown 리포트 |
| `scripts/run_eval.py`, `scripts/make_baseline_report.py` | 평가 실행, 리포트 생성 CLI |
| `tests/test_golden_sync_fifo.py`, `test_bugs.py`, `test_evaluator.py`, `test_eval_report.py` | 2, 9, 7, 2개 |

## 2. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 첫 골든 DUT | **sync FIFO** | async FIFO는 `empty` 비대칭 의심이 미확정이라 "정상 기준"으로 쓰면 평가가 오염됨. 이미 완료된 DUT이고 단일 클럭이라 참조 모델이 단순함. async FIFO는 Agent 완성 후 실전 사례로 유지 |
| TB 비교 방식 | 포트(`full`, `empty`, `data_out`)만 참조 모델과 비교하는 블랙박스 | 내부 신호를 보면 변형본이 내부 구조를 바꿀 때 비교 자체가 깨짐 |
| TB 타이밍 | 입력은 negedge, 비교는 posedge 2ns 뒤 | 경쟁 상태 방지 (reset은 비동기라 negedge 비교는 DUT와 모델의 갱신 순서에 따라 거짓 불일치가 날 수 있음) |
| TB 로그 규약 | 끝에 `[TB] PASS` 또는 `[TB] FAIL: ...` 한 줄, 상세는 `CHECK_FAIL ...` 최대 10개 | Phase 2 파서가 인식하는 형식. 상세 줄에는 `[TB]`나 `Error:` 접두를 쓰지 않아 파서와 겹치지 않음 |
| TB 자극 | 직접 시나리오 + 고정 seed 랜덤 4000사이클 | 결정적이면서 full/empty/동시 동작/랩/리셋을 모두 지남 |
| `timescale` | TB에서 지시문 제거 | 골든 RTL에 없어서 섞이면 xelab 에러 (3.1절) |
| 변형 저장 | 카탈로그가 단일 원본, 변형 RTL은 필요할 때 패치로 생성 | 파일로 저장하면 골든이 바뀔 때 조용히 어긋남. 패치 방식은 어긋나면 즉시 에러 |
| 패치 방식 | 한 줄 문자열 치환 + `expect_count` + `occurrence` | 같은 문장이 여러 곳에 있어도 몇 번째인지 지정하고, 개수가 달라지면 중단 |
| 줄바꿈 | 읽을 때 `\n`으로 통일 | Windows(CRLF) 파일에도 같은 줄에 같은 패치 (테스트로 확인) |
| 정답 메타데이터 | 파일, 줄 번호(패치 시점에 계산), 유형, 설명, `equivalent` | 줄 번호를 손으로 쓰지 않으므로 틀릴 수 없음. Agent에게는 보여주지 않는 정답지 |
| 동등 변형 | `equivalent: true`로 표시, 점수 분모에서 제외하고 따로 집계 | 관측 불가능한 변형을 못 잡았다고 TB나 Agent 탓으로 돌리지 않기 위함 |
| 실행기 분리 | `Runner = (files, top, workdir) -> Judged` | 판정 규칙과 집계를 시뮬레이터 없이 테스트하고, 실제 실행은 `xsim_runner()` 한 곳에만 둠 |
| 골든 우선 | 골든이 PASS가 아니면 변형을 실행하지 않고 중단 | 기준선이 깨지면 이후 수치가 무의미 |
| 종료 코드 | 하네스 자체의 문제(골든 실패, invalid, 동등 메타데이터 오류)일 때만 1 | 생존 변형은 TB가 약하다는 정보라 리포트에만 남김 |

### 판정 규칙

| 대상 | 결과 | 분류 |
|---|---|---|
| 일반 변형 | FAIL | `detected` |
| 일반 변형 | PASS, NO_VERDICT | `survived` |
| 일반 변형 | COMPILE_ERROR, ELAB_ERROR, TIMEOUT | `invalid` (경고, 점수 제외) |
| 동등 변형 | 생존 | `equivalent_ok` |
| 동등 변형 | 잡힘 | `equivalent_unexpected_detect` (메타데이터 오류 경고) |

`mutation score = detected / (detected + survived)`. invalid와 동등 변형은 분모에서 뺀다.

## 3. 측정과 발견

### 3.1 timescale 불일치 ✅

골든 RTL에는 `` `timescale ``이 없는데 TB에 `` `timescale 1ns / 1ps ``를 넣으면 **xelab에서** 에러가 난다 (컴파일 xvlog는 통과).

```
ERROR: [XSIM 43-4099] ... Module sync_fifo doesn't have a timescale but at least one module in design has a timescale.
```

- iverilog는 이를 에러로 보지 않아서 로컬 검증에서는 못 잡았고, xsim에서 처음 드러났다.
- 대응: TB에서 지시문을 제거해 xsim 기본값(1ns/1ps)을 사용. VCD는 1ps 해상도.
- 일반화: 사용자 RTL에는 timescale이 없고 LLM이 만든 TB에는 있는 경우가 흔할 것이다 (Phase 6). 어댑터 옵션이나 프롬프트 규칙이 필요하다 (⏸, 8절).

### 3.2 도달 불가 분기 (동등 변형의 근거) ✅

`fifo_ctrl.v`의 `2'b11`(동시 write+read) 안에 있는 `else if (empty)`, `else if (full)` 분기는 **top 기준으로 도달 불가능**하다. top이 `wr_en && !full`, `rd_en && !empty`로 먼저 걸러서 `fifo_ctrl`에는 empty나 full 상태에서 동시 write+read가 들어오지 않기 때문이다. 이 분기는 `fifo_ctrl`을 단독으로 쓸 때만 의미가 있는 방어 코드다.

- 이 두 분기를 바꾼 변형 `E01`, `E02`는 iverilog와 xsim 모두 PASS(생존)였다.
- 동등하다는 판단은 코드 읽기와 두 시뮬레이터의 결과에 근거한 것이고 **형식 검증을 한 것은 아니다** (⚠️).

### 3.3 sync FIFO의 동작 (참조 모델의 근거) ✅

| 항목 | 동작 |
|---|---|
| 읽기 | 동기 읽기: 클럭 에지에서 `data_out` 갱신, read가 없으면 값 유지, 리셋으로 지워지지 않음 |
| 리셋 | 비동기, active high. `data_out`은 초기에 X |
| full에서 write, empty에서 read | 무시 (top에서 차단) |
| 동시 write+read | empty면 write만, full이면 read만, 그 외는 둘 다 |

### 3.4 xsim과 iverilog 결과 비교 ✅

같은 TB와 같은 변형 19개를 두 시뮬레이터로 돌려 `status`와 첫 불일치 신호가 모두 같았다 (골든 PASS, 17개 detected, 동등 2개 PASS). 단 첫 불일치 **시각**은 xsim에서만 의미가 있다. iverilog는 `$timeformat` 단위를 다르게 처리해서 값이 어긋난다.

## 4. self-checking TB

- 참조 모델: 깊이 8, `m_count`, `m_wr`, `m_rd`, `m_mem[0:7]`, `m_dout`. read는 write 이전 값을 읽는다.
- 비교 대상: `full`, `empty`, `data_out` (`data_out`은 첫 read 이후부터, `!==`로 X도 불일치로 본다).
- 시나리오: 리셋, 8개 채우기와 overflow 3회, 8개 읽기와 underflow 3회, empty/full에서의 동시 동작, 포인터 랩, 데이터가 있을 때의 리셋, 랜덤 4구간(write 우세, read 우세, 균등, 양쪽 높음 + 가끔 리셋).
- 로컬(iverilog) 자극 통계: full 도달 786회, empty 도달 807회, overflow 568회, underflow 597회, 포인터 랩 225회, 리셋 24회, full과 empty에서의 동시 동작 각각 132회와 172회, 비교 4,099회.

## 5. 버그 카탈로그

| 유형 | 개수 | 예 |
|---|---|---|
| pointer | 6 (+ 동등 2) | read/write 포인터 정지, count가 2씩 감소 |
| flag | 3 | full이 7에서 켜짐, empty가 1에서 켜짐, full이 안 켜짐 |
| reset | 2 | 리셋 후 count나 rd_ptr이 1 |
| memory | 3 | 읽기 주소 오류, 저장 데이터 +1, 읽기가 rd_en과 무관 |
| guard | 2 | top의 full과 empty 가드 제거 |
| corner | 1 | count==7에서 동시 write+read 무시 |

카탈로그의 각 항목은 `id`, `type`, `file`, `find`, `replace`, `expect_count`, `occurrence`, `description`, `equivalent`를 갖는다. 로드 시 유형, 중복 id, 범위 밖 `occurrence`를 검사한다.

## 6. 검증 결과

### 6.1 실제 Vivado 평가 실행 ✅

`python -m scripts.run_eval` (골든 1 + 변형 19, 총 221초, 실행당 약 11초).

| id | 유형 | 결과 | 첫 불일치 |
|---|---|---|---|
| B01_read_ptr_no_inc | pointer | detected | `data_out` @167 ns |
| B02_write_ptr_no_inc | pointer | detected | `data_out` @157 ns |
| B03_both_rd_ptr_stuck | pointer | detected | `data_out` @297 ns |
| B04_both_wr_ptr_stuck | pointer | detected | `data_out` @397 ns |
| B05_read_count_dec2 | pointer | detected | `empty` @187 ns |
| B06_write_count_no_inc | pointer | detected | `empty` @37 ns |
| B07_full_at_7 | flag | detected | `full` @97 ns |
| B08_empty_at_1 | flag | detected | `empty` @27 ns |
| B09_full_never | flag | detected | `full` @107 ns |
| B10_reset_count_one | reset | detected | `empty` @27 ns |
| B11_reset_rd_ptr_one | reset | detected | `data_out` @157 ns |
| B12_mem_read_addr_wr | memory | detected | `data_out` @167 ns |
| B13_mem_write_data_plus1 | memory | detected | `data_out` @157 ns |
| B14_mem_read_ungated | memory | detected | `data_out` @237 ns |
| B15_no_full_guard | guard | detected | `data_out` @157 ns |
| B16_no_empty_guard | guard | detected | `data_out` @237 ns |
| B17_both_ignored_at_7 | corner | detected | `data_out` @417 ns |
| E01_dead_full_branch | 동등 | equivalent_ok | - |
| E02_dead_empty_branch | 동등 | equivalent_ok | - |

- 골든 PASS, detected 17, survived 0, invalid 0, equivalent_ok 2, **mutation score 100%**.
- 탐지 시점: 최소 27 ns, 최대 417 ns. B17(corner)이 가장 늦게 잡혔다. 랜덤 구간의 우연에 기대는 유형이다.
- 시각 단위: xsim에서는 `t=<n> ns` 형식으로 찍혀 ps로 정상 변환됨 (✅).

### 6.2 자동 테스트

| 파일 | 개수 | 내용 |
|---|---|---|
| `test_golden_sync_fifo.py` | 2 | 골든 PASS(Vivado), full 기준 변형은 FAIL(Vivado) |
| `test_bugs.py` | 9 | 카탈로그 스키마, 모든 패치의 한 줄 diff, 줄 번호, 골든 불변, `expect_count` 불일치 오류, CRLF, 동등 변형 목록 |
| `test_evaluator.py` | 7 | CHECK_FAIL 파서, 분류 규칙, 골든 우선과 중단, 변형 RTL 전달, 집계, JSON 직렬화 |
| `test_eval_report.py` | 2 | 리포트 렌더링, 중단과 점수 없음 처리 |

전체 기대값은 98개. 89개까지는 실행 확인했고, 평가와 리포트 테스트 9개는 적용 후 확인이 필요하다 (⚠️). 평가와 리포트 테스트는 Vivado 없이 도는 순수 파이썬이다.

## 7. 한계 및 미확인

| 항목 | 상태 | 비고 |
|---|---|---|
| mutation score 100%의 의미 | ⚠️ | "이 변형 세트를 TB가 모두 잡는다"이지 TB가 완전하다는 뜻이 아님. 변형은 한 줄 치환 단일 버그 |
| 동등 변형의 형식 검증 | ⏸ | 코드 읽기와 시뮬레이션 결과로만 판단 |
| 랜덤 구간의 seed 의존 | ⚠️ | 늦게 잡히는 변형(B17)은 seed나 길이를 바꾸면 결과가 달라질 수 있음 |
| 다중 버그, 타이밍, 클럭 도메인 교차 버그 | ⏸ | 현재 세트에 없음 |
| 골든 DUT가 sync FIFO 하나뿐 | ⏸ | UART, SPI, I2C로 확장 예정 |
| async FIFO의 self-checking TB | ⏸ | 아직 없음. `empty` 비대칭 의심은 계속 보류 |
| 어댑터의 기본 timescale 옵션 | ⏸ | 지금은 TB에서 지시문을 빼는 것으로 회피 |
| LLM이 만든 TB의 평가 | ✅ | Phase 6에서 측정: 골든 PASS, mutation score 100% (1회 생성, `docs/NOTES_ps6.md`) |
| Agent의 원인 위치 정확도 | ❓ | Phase 7에서 `bugs.json`의 파일, 줄, 유형과 대조 |

## 8. 작업 중 얻은 교훈

- **최종 검증은 실제 시뮬레이터(xsim)로 한다.** iverilog가 PASS한 TB가 xsim에서 timescale 에러로 막혔다. 빠른 로컬 검증은 쓰되 판정은 xsim으로.
- **"못 잡은 것"과 "잡을 수 없는 것"을 분리한다.** 두 변형이 생존했을 때 TB가 약한 줄 알았는데, 도달 불가 코드였다. 이 구분이 없으면 이후 Agent 평가가 오염된다. 부수 효과로 `fifo_ctrl`의 방어 코드가 사실상 죽은 코드라는 코드 리뷰 소견도 얻었다.
- **정답지는 손으로 쓰지 않고 계산한다.** 줄 번호를 패치 시점에 계산하고 `expect_count`로 골든과의 불일치를 즉시 잡는다.
- **파일 이동은 테스트가 가장 먼저 알려 준다.** `dut` 폴더 이름(`sync_fifo.v`)이 어긋나고 Phase 0용 파일이 함께 옮겨져 기존 테스트 5개가 실패했다. 폴더 구조가 바뀌면 `pytest` 개수부터 확인한다.
- **TB 로그는 파서 규약에 맞춘다.** 마커 한 줄만 `[TB] PASS/FAIL`로 쓰고 상세는 다른 접두로 분리해서 Phase 2 파서와 간섭하지 않게 했다.

## 9. 다음 단계 (Phase 5: RTL Analyzer) — ✅ 완료, 결과는 `docs/NOTES_ps5.md`

| 확인된 사실 | 설계 |
|---|---|
| TB Generator(Phase 6)는 DUT의 포트, 파라미터, 클럭, 리셋, 계층을 알아야 함 | 이 정보를 결정적으로 추출하는 RTL Analyzer를 먼저 만듦 |
| 골든 3개 모듈(`sync_fifo`, `fifo_ctrl`, `fifo_mem`)과 async FIFO 5개 모듈이 정답을 아는 입력 | 두 DUT로 추출 결과를 검증 |
| 리셋이 비동기 active high (`posedge reset`) | 리셋 극성과 동기/비동기 판별 규칙 필요 |
| RTL에 timescale이 없음 | 분석 결과에 timescale 유무를 포함해 TB 생성 규칙에 연결 |

| # | 내용 |
|---|---|
| 5-1 | 모듈과 포트 파서 (방향, 폭, 이름) |
| 5-2 | 인스턴스 계층 트리 (top 후보 추정) |
| 5-3 | 클럭, 리셋, 파라미터, FSM 후보 휴리스틱 |
| 5-4 | LLM에 넘길 요약 JSON 형식과 검증 |

## 10. 명령어 요약

```powershell
cd C:\Users\Junyoung\Desktop\Verilog\Agent
.\.venv\Scripts\Activate.ps1

pytest -q                                              # 98 passed 기대 (Vivado 포함 약 1분)

# 골든 한 번 실행
python -m scripts.run_once --top sync_fifo_sc_tb --label golden --files dut/sync_fifo/rtl/sync_fifo.v dut/sync_fifo/rtl/fifo_ctrl.v dut/sync_fifo/rtl/fifo_mem.v dut/sync_fifo/tb/tb_sync_fifo_sc.v

python -m scripts.run_eval                             # 골든 + 변형 19개 (약 4분)
python -m scripts.run_eval --only B07 B17              # 일부만
python -m scripts.make_baseline_report                 # 최근 결과 -> reports/baseline_sync_fifo.md
```