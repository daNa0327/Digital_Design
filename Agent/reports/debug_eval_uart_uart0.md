# Debug Agent 평가: uart (uart0)

입력 TB: `C:/Users/Junyoung/Desktop/Verilog/Agent/dut/uart/tb/tb_uart_sc.v` (사람이 쓴 self-checking TB, 골든 PASS 검증됨). 최대 단계 8, 줄 허용 오차 2줄.
프롬프트 버전(시스템 프롬프트 해시): c6f81dc0ff61

## 요약

평가된 케이스 30개 (사람 TB가 FAIL시키지 않아 제외 0, 동등 변형 제외 2, 미실행 0).

| 지표 | 값 |
|---|---|
| 보고서를 낸 비율 | 90% |
| 파일을 맞힘 | 80% |
| **정확한 줄** | 63% |
| **정답 줄 ±2줄 이내** | 63% |
| 평균 단계 수 (보고서를 낸 케이스) | 7.4 |
| 평균 도구 호출 수 | 5.7 |
| LLM 호출 (캐시 제외) / 캐시 | 252 / 0 |
| 형식 오류율 (단계 기준) | 10% |
| 거부된 보고서 수 | 1 |
| STOP이 아닌 이유로 끝난 응답 수 (MAX_TOKENS 등) | 46 |
| 빈 응답 재시도 (보냄 / 단계를 이어간 횟수) | 30 / 17 |
| 평탄한 도구 호출 정규화 (형식 오류였을 호출) | 4 |
| 토큰 입력 / 출력 | 1124030 / 25455 |

### 도구 사용

| 도구 | 호출 수 |
|---|---|
| read_rtl | 73 |
| propose_fix | 28 |
| search_rtl | 25 |
| rerun_sim | 21 |
| read_tb | 13 |
| list_signals | 11 |
| get_log_snippet | 1 |

로그·TB·파형 조회(`get_log_snippet`, `read_tb`, `read_vcd_signal`, `sample_signals`)를 한 번이라도 쓴 케이스: 5/30. 0에 가까우면 이 평가는 실패 시뮬레이션 디버깅이 아니라 RTL 코드 리뷰 능력을 재고 있다.

### 수정안 검증 (7-5)

원본 사람 TB로 재시뮬레이션한 케이스 30개. Agent가 rerun_sim을 직접 쓴 횟수 21.

| 분류 | 개수 | 뜻 |
|---|---|---|
| fixed_golden | 16 | PASS, 골든 RTL과 같음 (원래 코드로 복원) |
| fixed_pass | 1 | PASS이지만 골든과 다름 (대안 수정이거나 TB 구멍 — diff를 직접 확인) |
| still_fail | 2 | 적용해도 FAIL |
| unverified | 0 | 적용/시뮬레이션 실패 |
| no_fix | 11 | 보고서가 수정안을 지목하지 않음 |

위치는 맞혔는데(±줄 이내) 수정안이 없거나 실패한 케이스: B11_tx_busy_reset_high, B20_rx_7bits

### 결과 분류

| 분류 | 개수 |
|---|---|
| exact | 19 |
| near | 0 |
| wrong_line | 5 |
| wrong_file | 2 |
| not_rtl_bug | 1 |
| no_report | 3 |

### 버그 유형별

| 유형 | 케이스 | ±줄 이내 | 정확 |
|---|---|---|---|
| corner | 10 | 6 | 6 |
| flag | 4 | 3 | 3 |
| guard | 5 | 2 | 2 |
| pointer | 6 | 5 | 5 |
| reset | 5 | 3 | 3 |

### 확신도와 정답률 (보고서를 낸 케이스)

| 확신도 | 케이스 | ±줄 이내 |
|---|---|---|
| high | 25 | 19 |
| medium | 1 | 0 |
| low | 1 | 0 |

⚠️ 확신도 high인데 틀린 케이스: B02_baud_wrap_one, B04_baud_tick_stuck, B05_tx_msb_first, B15_tx_ignore_tick, B22_rx_no_stop_check, B29_rx_data_period_short

## 케이스별

| 버그 | 유형 | 정답 | Agent | 분류 | 수정안 | 상태 | 단계 | 호출 |
|---|---|---|---|---|---|---|---|---|
| B01_baud_period_short | corner | rtl/Baud_Rate_Generator.v:19 | rtl/Baud_Rate_Generator.v:19 | exact | fixed_golden | final | 6 | 8 |
| B02_baud_wrap_one | corner | rtl/Baud_Rate_Generator.v:20 | rtl/UART_TX.v:30 | wrong_file | no_fix | final | 8 | 8 |
| B03_baud_reset_count | reset | rtl/Baud_Rate_Generator.v:16 | rtl/UART_TX.v:31 | wrong_file | no_fix | final | 8 | 9 |
| B04_baud_tick_stuck | flag | rtl/Baud_Rate_Generator.v:25 | rtl/Baud_Rate_Generator.v:10 | wrong_line | no_fix | final | 8 | 11 |
| B05_tx_msb_first | pointer | rtl/UART_TX.v:45 | rtl/UART_TX.v:29 | wrong_line | no_fix | final | 8 | 9 |
| B06_tx_7bits | pointer | rtl/UART_TX.v:47 | rtl/UART_TX.v:47 | exact | fixed_golden | final | 8 | 12 |
| B07_tx_bitidx_no_clear | pointer | rtl/UART_TX.v:31 | rtl/UART_TX.v:31 | exact | fixed_golden | final | 8 | 9 |
| B08_tx_start_bit_high | corner | rtl/UART_TX.v:40 | rtl/UART_TX.v:1 | not_rtl_bug | no_fix | final | 8 | 8 |
| B09_tx_stop_bit_low | corner | rtl/UART_TX.v:55 | rtl/UART_TX.v:55 | exact | fixed_golden | final | 6 | 6 |
| B10_tx_reset_low | reset | rtl/UART_TX.v:22 | - | no_report | no_fix | max_steps | 8 | 9 |
| B11_tx_busy_reset_high | reset | rtl/UART_TX.v:23 | rtl/UART_TX.v:23 | exact | no_fix | final | 8 | 10 |
| B12_tx_busy_late | flag | rtl/UART_TX.v:41 | rtl/UART_TX.v:41 | exact | fixed_golden | final | 8 | 8 |
| B13_tx_busy_early_fall | flag | rtl/UART_TX.v:56 | rtl/UART_TX.v:56 | exact | fixed_golden | final | 7 | 7 |
| B14_tx_no_latch | guard | rtl/UART_TX.v:45 | rtl/UART_TX.v:45 | exact | fixed_golden | final | 6 | 6 |
| B15_tx_ignore_tick | corner | rtl/UART_TX.v:26 | rtl/UART_TX.v:20 | wrong_line | no_fix | final | 8 | 8 |
| B16_tx_auto_restart | guard | rtl/UART_TX.v:57 | - | no_report | no_fix | max_steps | 8 | 8 |
| B17_tx_skip_stop | corner | rtl/UART_TX.v:48 | rtl/UART_TX.v:48 | exact | fixed_golden | final | 7 | 7 |
| B18_rx_sample_edge | corner | rtl/UART_RX.v:44 | rtl/UART_RX.v:44 | exact | fixed_golden | final | 8 | 10 |
| B19_rx_msb_first | pointer | rtl/UART_RX.v:56 | rtl/UART_RX.v:56 | exact | fixed_golden | final | 6 | 7 |
| B20_rx_7bits | pointer | rtl/UART_RX.v:57 | rtl/UART_RX.v:57 | exact | still_fail | final | 8 | 10 |
| B21_rx_bitidx_no_clear | pointer | rtl/UART_RX.v:46 | rtl/UART_RX.v:46 | exact | fixed_golden | final | 7 | 8 |
| B22_rx_no_stop_check | guard | rtl/UART_RX.v:70 | rtl/UART_RX.v:44 | wrong_line | no_fix | final | 8 | 8 |
| B23_rx_start_on_high | guard | rtl/UART_RX.v:38 | rtl/UART_RX.v:38 | exact | fixed_golden | final | 7 | 7 |
| B24_rx_valid_stuck | flag | rtl/UART_RX.v:37 | rtl/UART_RX.v:37 | exact | fixed_golden | final | 6 | 6 |
| B25_rx_valid_reset_high | reset | rtl/UART_RX.v:32 | rtl/UART_RX.v:32 | exact | fixed_golden | final | 8 | 8 |
| B26_rx_data_reset_ff | reset | rtl/UART_RX.v:30 | rtl/UART_RX.v:30 | exact | fixed_pass | final | 8 | 11 |
| B27_rx_count_no_clear | corner | rtl/UART_RX.v:45 | rtl/UART_RX.v:45 | exact | fixed_golden | final | 8 | 9 |
| B28_rx_stop_half | corner | rtl/UART_RX.v:67 | rtl/UART_RX.v:67 | exact | fixed_golden | final | 6 | 6 |
| B29_rx_data_period_short | corner | rtl/UART_RX.v:54 | rtl/UART_RX.v:67 | wrong_line | still_fail | final | 8 | 10 |
| B30_top_tick_tied | guard | rtl/UART.v:26 | - | no_report | no_fix | format_errors | 6 | 9 |
| E01_rx_counter_wider | corner | - | - | equivalent_skipped | - | - | - | - |
| E02_tx_idle_redundant | flag | - | - | equivalent_skipped | - | - | - | - |

## 해석할 때 주의

- 케이스가 30개뿐이고 버그는 한 줄 치환 단일 버그다. 비율은 통계가 아니라 이 세트에서의 관찰이다.
- 정답 줄은 패치가 적용된 줄이다. 원인과 증상이 다른 줄이면 증상 줄을 지목해도 `near`/`wrong_line`이 된다.
- 사람 TB가 쓴 신호 이름, 기대값 계산이 Agent에게 보이므로 LLM이 만든 TB의 실패에서는 결과가 다를 수 있다.
- 수정안 PASS는 "사람 TB가 못 잡는 오류가 없다"는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 본다.
- 같은 변형 세트로 TB 평가와 Agent 평가를 모두 했다. 세트에 맞춰 프롬프트를 고치면 이 수치는 낙관적이 된다.
