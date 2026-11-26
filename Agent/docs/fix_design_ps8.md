# Phase 8 Debug Agent 수정 설계 (spi0 이후)

> 작성 2026-11-26. 근거는 sync_fifo v0e(17개)와 SPI spi0(30개)만 쓴다.
> UART(uart0)와 I2C(i2c0)는 **held-out 세트**라 케이스를 들여다보지 않고 수치만 기록한다 (수정 설계에 쓰면 일반화 근거가 사라진다).
> 이 문서는 결과를 보기 전에 판정 기준을 정해 두는 용도다. 실험 후 기준을 바꾸면 바꿨다고 기록한다.

## 1. 측정된 문제 (근거 수치)

| 문제 | sync_fifo v0e | SPI spi0 | 근거 위치 |
|---|---|---|---|
| 위치 정확도 (exact) | 15/17 (88%) | 16/30 (53%), 파일 73% | `results.json` summary |
| 수정안 | golden 12, pass 2, fail 0, no_fix 3 | golden 9, pass 4, fail 0, no_fix 17 | `fix_check.json` |
| 8단계를 모두 쓴 케이스 | 12/17 | 26/30 | steps |
| `max_steps`로 끝남 | 1 | 2 (B05, B30) | run_status |
| "단계 부족"이라고 스스로 쓴 `unknown` | 0 | 3 (B07, B12, B19) | report.root_cause |
| 형식 오류가 쓴 단계 | 9 / 125 (7%) | 18 / 230 (8%) | step kind |
| 같은 파일 `read_rtl` 반복 | — | 22회 | steps |
| `list_signals` | — | 20회 (첫 실패 신호 이름은 이미 알고 있음) | steps |
| 로그/TB/파형 도구를 쓴 케이스 | 0/17 | 9/30 | evidence_tool_cases |
| 클럭 로직 유령 주장 | 1 (`count <= count`) | **5** (B03, B06, B09, B10, B13: "DONE이 1주기뿐") | report.root_cause |

SPI 230단계 중 약 70단계(형식 오류 18 + 중복 읽기 22 + `list_signals` 20 + 거부 1 + ...)가 원인 조사에 직접 쓰이지 않았다.

### 유령 주장의 공통 구조
골든 `Master_FSM`은 TRANSFER 마지막 에지에서 `done <= 1`을 넣고 DONE 상태에서 한 번 더 `done <= 1`을 유지해 spec대로 2주기다.
Agent는 DONE 블록만 읽고 "다음 에지에 IDLE로 가므로 1주기"라고 결론냈다. 다섯 케이스 모두 **파형을 보지 않았고**(`read_vcd_signal`/`sample_signals` 0회) **수정안을 rerun_sim으로 확인하지도 않았다**.
즉 "레지스터 값은 이전 상태에서 넣은 값이 이어진다"를 놓친 추론을 검증 없이 보고했다. sync_fifo의 `count <= count`와 같은 계열이다.

### 초기 메시지에서 버려지는 증거
TB는 `CHECK_FAIL t=.. sig=.. exp=.. got=.. (bit=3 CS=0 busy=1 done=0)`처럼 실패 순간의 상태를 괄호에 찍는다.
`core/evaluator.py`의 `parse_check_fails`는 t/sig/exp/got만 남기고 괄호를 버린다 → Agent는 그 문맥을 보려면 `get_log_snippet`을 써야 하는데 30케이스 중 1번만 썼다.

## 2. 수정안 (적용 순서 = 비용이 싸고 효과를 분리하기 쉬운 순서)

| ID | 대상 문제 | 변경 | 파일 | 규모 |
|---|---|---|---|---|
| F1 | 단계 한도 | (a) 형식 오류와 거부된 보고서는 조사 단계로 세지 않는다. 대신 별도 상한(케이스당 추가 3턴)을 둔다. (b) `max_steps` 8 → 10 | `core/debug_loop.py`, CLI 기본값 | 작음 |
| F2a | 증거 미사용 | 초기 메시지의 실패 줄에 CHECK_FAIL 원문(괄호 문맥 포함)을 그대로 싣는다 | `core/evaluator.py`(CheckFail에 raw 추가), `core/debug_protocol.py` | 아주 작음 |
| F2b | 증거 미사용, 단계 낭비 | 첫 실패 신호를 VCD에서 찾을 수 있으면 실패 시각 전후 파형 샘플을 초기 메시지에 미리 넣는다 (`list_signals` + `read_vcd_signal` 2~3단계 절약) | `core/debug_eval.py` 또는 `debug_protocol.py`, `debug_tools.py` 재사용 | 중간 |
| F3 | 유령 주장 | (a) 규칙 8 추가: "신호 유지 시간, 전이 시점 같은 타이밍 결함을 주장하기 전에 파형으로 확인하라. 레지스터 출력은 이전 상태에서 넣은 값이 유지된다 — 그 신호를 넣는 모든 상태를 추적하라." (b) 보고서 검증: `rtl_bug` 보고서는 증거에 로그/TB/파형 도구 또는 rerun_sim 단계를 하나 이상 인용해야 한다 (RTL만 읽고 낸 보고서는 1회 거부 + 안내) | `core/debug_protocol.py`, `core/debug_loop.py`(`semantic_problems`) | 작음~중간 |
| (보류) F4 | 형식 오류 원인 | Gemini `MALFORMED_FUNCTION_CALL`, 한 응답의 여러 액션, 로그 500자 제한 (CLAUDE.local §B-4) | — | F1이 피해를 줄이므로 뒤로 미룸 |

### 각 수정의 기대와 위험

| ID | 기대 효과 | 위험 |
|---|---|---|
| F1 | `max_steps`/"단계 부족" unknown 감소, rerun_sim까지 가는 케이스 증가 | 호출 수 약 20% 증가 (일일 500회 한도), 단계가 늘어도 같은 파일만 더 읽을 수 있음 |
| F2a | 실패 순간 상태를 첫 턴부터 사용, 유령 주장 일부 차단(예: done 시점이 로그에 보임) | 거의 없음 |
| F2b | `list_signals` 20회 감소, 파형 기반 추론 증가 | 초기 메시지가 길어져 토큰 증가, 신호 이름 매핑 실패 시 효과 없음 |
| F3 | 유령 주장 5 → 1 이하, wrong_line 감소 | 지금 RTL만 읽고 맞히던 exact 케이스가 거부되어 단계를 더 씀 → F1 없이 넣으면 오히려 unknown 증가 가능. 그래서 F1 뒤에 둔다 |

## 3. 실험 계획

- **개발 세트**: SPI(30). **회귀 세트**: sync_fifo(17). **held-out**: UART(30, 사용자 RTL), I2C(30, Claude 작성이라 가중치 낮음).
- 기준선: spi0, v0e, uart0, i2c0 (모두 수정 전 Agent, `--no-cache`).
- 수정은 한 번에 한 묶음씩 적용하고 SPI로 측정한다: `spi1`(F1+F2a) → `spi2`(+F2b) → `spi3`(+F3).
  F1과 F2a를 묶는 이유: F2a는 정보 손실을 고치는 것이라 독립 효과를 볼 가치가 낮고, 할당량(하루 500회, SPI 1회 약 250~300회)이 빠듯하다.
- 마지막 버전으로 sync_fifo, UART, I2C를 다시 측정해 기준선과 비교한다.
- 각 측정은 1회 실행이다. sync_fifo v0d/v0e 사이에서도 결과가 크게 달랐으므로 **±3케이스 이내 차이는 잡음으로 본다.**

### 미리 정하는 판정 기준 (최종 버전 기준)

| 지표 | 목표 |
|---|---|
| SPI exact | 16/30 → 21/30 이상 (+5케이스) |
| 클럭 로직 유령 주장 (SPI) | 5 → 1 이하 |
| `max_steps` + "단계 부족" unknown (SPI) | 5 → 1 이하 |
| still_fail (틀린 수정이 보고서에 실림) | 모든 세트에서 0 유지 |
| sync_fifo exact (회귀) | 13/17 이상 유지 |
| UART/I2C exact | uart0/i2c0 대비 하락하지 않고 SPI와 같은 방향으로 개선 |
| 평균 호출 수 | 케이스당 10회 이하 (무료 한도 안에서 하루 2세트) |

보조 지표(채점 한계 보완): B01처럼 다른 줄을 고쳤지만 rerun_sim PASS인 경우를 "기능적 위치 정답"으로 따로 센다. 주 지표(exact)의 정의는 바꾸지 않는다.

## 4. 하지 않는 것
- UART/I2C 케이스 내용을 보고 프롬프트나 도구를 고치지 않는다.
- 모델 교체(유료 모델)는 하지 않는다. 비용 0 원칙.
- 수정 전후를 다른 TB나 카탈로그로 비교하지 않는다.
