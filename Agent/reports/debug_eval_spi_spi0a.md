# Debug Agent 평가: spi (spi0a)

입력 TB: `C:/Users/Junyoung/Desktop/Verilog/Agent/dut/spi/tb/tb_spi_sc.v` (사람이 쓴 self-checking TB, 골든 PASS 검증됨). 최대 단계 8, 줄 허용 오차 2줄.
프롬프트 버전(시스템 프롬프트 해시): c6f81dc0ff61

⚠️ **중간에 멈춤**: B19_rx_always_shift: llm_error (LLMTransientError: 서버 오류 503: This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.). 아래 수치는 끝난 케이스만의 값이다. 같은 명령에 `--resume`을 붙여 이어서 실행한다.

## 요약

평가된 케이스 3개 (사람 TB가 FAIL시키지 않아 제외 0, 동등 변형 제외 0, 미실행 0).

| 지표 | 값 |
|---|---|
| 보고서를 낸 비율 | 67% |
| 파일을 맞힘 | 67% |
| **정확한 줄** | 67% |
| **정답 줄 ±2줄 이내** | 67% |
| 평균 단계 수 (보고서를 낸 케이스) | 6.5 |
| 평균 도구 호출 수 | 5.3 |
| LLM 호출 (캐시 제외) / 캐시 | 21 / 0 |
| 형식 오류율 (단계 기준) | 10% |
| 거부된 보고서 수 | 0 |
| STOP이 아닌 이유로 끝난 응답 수 (MAX_TOKENS 등) | 2 |
| 빈 응답 재시도 (보냄 / 단계를 이어간 횟수) | 1 / 0 |
| 평탄한 도구 호출 정규화 (형식 오류였을 호출) | 0 |
| 토큰 입력 / 출력 | 87445 / 1927 |

### 도구 사용

| 도구 | 호출 수 |
|---|---|
| read_rtl | 5 |
| search_rtl | 3 |
| propose_fix | 2 |
| read_tb | 2 |
| rerun_sim | 2 |
| list_signals | 1 |
| read_vcd_signal | 1 |

로그·TB·파형 조회(`get_log_snippet`, `read_tb`, `read_vcd_signal`, `sample_signals`)를 한 번이라도 쓴 케이스: 2/3. 0에 가까우면 이 평가는 실패 시뮬레이션 디버깅이 아니라 RTL 코드 리뷰 능력을 재고 있다.

### 수정안 검증 (7-5)

원본 사람 TB로 재시뮬레이션한 케이스 2개. Agent가 rerun_sim을 직접 쓴 횟수 2.

| 분류 | 개수 | 뜻 |
|---|---|---|
| fixed_golden | 2 | PASS, 골든 RTL과 같음 (원래 코드로 복원) |
| fixed_pass | 0 | PASS이지만 골든과 다름 (대안 수정이거나 TB 구멍 — diff를 직접 확인) |
| still_fail | 0 | 적용해도 FAIL |
| unverified | 0 | 적용/시뮬레이션 실패 |
| no_fix | 0 | 보고서가 수정안을 지목하지 않음 |

위치는 맞혔는데(±줄 이내) 수정안이 없거나 실패한 케이스: 없음

### 결과 분류

| 분류 | 개수 |
|---|---|
| exact | 2 |
| near | 0 |
| wrong_line | 0 |
| wrong_file | 0 |
| not_rtl_bug | 0 |
| no_report | 1 |

### 버그 유형별

| 유형 | 케이스 | ±줄 이내 | 정확 |
|---|---|---|---|
| corner | 1 | 1 | 1 |
| guard | 1 | 0 | 0 |
| pointer | 1 | 1 | 1 |

### 확신도와 정답률 (보고서를 낸 케이스)

| 확신도 | 케이스 | ±줄 이내 |
|---|---|---|
| high | 2 | 2 |

## 케이스별

| 버그 | 유형 | 정답 | Agent | 분류 | 수정안 | 상태 | 단계 | 호출 |
|---|---|---|---|---|---|---|---|---|
| B01_div_period_off | corner | rtl/clock_divider.v:19 | rtl/clock_divider.v:19 | exact | fixed_golden | final | 5 | 5 |
| B15_tx_lsb_first | pointer | rtl/Master_TX.v:13 | rtl/Master_TX.v:13 | exact | fixed_golden | final | 8 | 9 |
| B19_rx_always_shift | guard | rtl/Master_RX.v:14 | - | no_report | - | llm_error | 7 | 7 |

## 해석할 때 주의

- 케이스가 3개뿐이고 버그는 한 줄 치환 단일 버그다. 비율은 통계가 아니라 이 세트에서의 관찰이다.
- 정답 줄은 패치가 적용된 줄이다. 원인과 증상이 다른 줄이면 증상 줄을 지목해도 `near`/`wrong_line`이 된다.
- 사람 TB가 쓴 신호 이름, 기대값 계산이 Agent에게 보이므로 LLM이 만든 TB의 실패에서는 결과가 다를 수 있다.
- 수정안 PASS는 "사람 TB가 못 잡는 오류가 없다"는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 본다.
- 같은 변형 세트로 TB 평가와 Agent 평가를 모두 했다. 세트에 맞춰 프롬프트를 고치면 이 수치는 낙관적이 된다.
