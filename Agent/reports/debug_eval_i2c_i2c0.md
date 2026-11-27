# Debug Agent 평가: i2c (i2c0)

입력 TB: `C:/Users/Junyoung/Desktop/Verilog/Agent/dut/i2c/tb/tb_i2c_sc.v` (사람이 쓴 self-checking TB, 골든 PASS 검증됨). 최대 단계 8, 줄 허용 오차 2줄.
프롬프트 버전(시스템 프롬프트 해시): c6f81dc0ff61

## 요약

평가된 케이스 30개 (사람 TB가 FAIL시키지 않아 제외 0, 동등 변형 제외 2, 미실행 0).

| 지표 | 값 |
|---|---|
| 보고서를 낸 비율 | 100% |
| 파일을 맞힘 | 37% |
| **정확한 줄** | 23% |
| **정답 줄 ±2줄 이내** | 27% |
| 평균 단계 수 (보고서를 낸 케이스) | 8.0 |
| 평균 도구 호출 수 | 6.4 |
| LLM 호출 (캐시 제외) / 캐시 | 257 / 0 |
| 형식 오류율 (단계 기준) | 7% |
| 거부된 보고서 수 | 0 |
| STOP이 아닌 이유로 끝난 응답 수 (MAX_TOKENS 등) | 36 |
| 빈 응답 재시도 (보냄 / 단계를 이어간 횟수) | 18 / 11 |
| 평탄한 도구 호출 정규화 (형식 오류였을 호출) | 1 |
| 토큰 입력 / 출력 | 1338974 / 28522 |

### 도구 사용

| 도구 | 호출 수 |
|---|---|
| read_rtl | 85 |
| search_rtl | 52 |
| read_tb | 34 |
| list_signals | 12 |
| propose_fix | 5 |
| rerun_sim | 3 |
| get_log_snippet | 2 |

로그·TB·파형 조회(`get_log_snippet`, `read_tb`, `read_vcd_signal`, `sample_signals`)를 한 번이라도 쓴 케이스: 13/30. 0에 가까우면 이 평가는 실패 시뮬레이션 디버깅이 아니라 RTL 코드 리뷰 능력을 재고 있다.

### 수정안 검증 (7-5)

원본 사람 TB로 재시뮬레이션한 케이스 30개. Agent가 rerun_sim을 직접 쓴 횟수 3.

| 분류 | 개수 | 뜻 |
|---|---|---|
| fixed_golden | 2 | PASS, 골든 RTL과 같음 (원래 코드로 복원) |
| fixed_pass | 1 | PASS이지만 골든과 다름 (대안 수정이거나 TB 구멍 — diff를 직접 확인) |
| still_fail | 0 | 적용해도 FAIL |
| unverified | 0 | 적용/시뮬레이션 실패 |
| no_fix | 27 | 보고서가 수정안을 지목하지 않음 |

위치는 맞혔는데(±줄 이내) 수정안이 없거나 실패한 케이스: B01_div_period_short, B08_fsm_ignore_nack, B13_fsm_done_short, B16_fsm_reset_scl_low, B27_slv_no_rx_latch

### 결과 분류

| 분류 | 개수 |
|---|---|
| exact | 7 |
| near | 1 |
| wrong_line | 3 |
| wrong_file | 9 |
| not_rtl_bug | 10 |
| no_report | 0 |

### 버그 유형별

| 유형 | 케이스 | ±줄 이내 | 정확 |
|---|---|---|---|
| corner | 7 | 2 | 2 |
| flag | 7 | 2 | 1 |
| guard | 5 | 1 | 1 |
| pointer | 8 | 1 | 1 |
| reset | 3 | 2 | 2 |

### 확신도와 정답률 (보고서를 낸 케이스)

| 확신도 | 케이스 | ±줄 이내 |
|---|---|---|
| high | 15 | 8 |
| low | 10 | 0 |
| medium | 5 | 0 |

⚠️ 확신도 high인데 틀린 케이스: B03_div_tick_stuck, B07_fsm_7bits_rx, B17_fsm_no_load_data, B19_mtx_addr_order, B22_slv_addr_bits, B23_slv_no_addr_ack, B26_slv_shift_on_fall

## 케이스별

| 버그 | 유형 | 정답 | Agent | 분류 | 수정안 | 상태 | 단계 | 호출 |
|---|---|---|---|---|---|---|---|---|
| B01_div_period_short | corner | rtl/clock_divider.v:20 | rtl/clock_divider.v:20 | exact | no_fix | final | 8 | 11 |
| B02_div_count_step2 | corner | rtl/clock_divider.v:25 | rtl/clock_divider.v:25 | exact | fixed_golden | final | 8 | 8 |
| B03_div_tick_stuck | flag | rtl/clock_divider.v:26 | rtl/Master_FSM.v:126 | wrong_file | no_fix | final | 8 | 8 |
| B04_fsm_no_start_cond | corner | rtl/Master_FSM.v:98 | rtl/Master_FSM.v:126 | not_rtl_bug | no_fix | final | 8 | 8 |
| B05_fsm_tx_inverted | flag | rtl/Master_FSM.v:106 | -:- | not_rtl_bug | no_fix | final | 8 | 9 |
| B06_fsm_7bits_tx | pointer | rtl/Master_FSM.v:112 | -:- | not_rtl_bug | no_fix | final | 8 | 9 |
| B07_fsm_7bits_rx | pointer | rtl/Master_FSM.v:147 | rtl/Master_FSM.v:113 | wrong_line | no_fix | final | 8 | 8 |
| B08_fsm_ignore_nack | guard | rtl/Master_FSM.v:123 | rtl/Master_FSM.v:123 | exact | no_fix | final | 8 | 8 |
| B09_fsm_ack_error_sticky | flag | rtl/Master_FSM.v:91 | rtl/Master_FSM.v:1 | wrong_line | no_fix | final | 8 | 8 |
| B10_fsm_nack_continue | guard | rtl/Master_FSM.v:126 | rtl/Master_FSM.v:1 | not_rtl_bug | no_fix | final | 8 | 8 |
| B11_fsm_rw_swapped | guard | rtl/Master_FSM.v:128 | rtl/Master_FSM.v:1 | not_rtl_bug | no_fix | final | 8 | 8 |
| B12_fsm_no_stop_cond | corner | rtl/Master_FSM.v:169 | rtl/Master_FSM.v:164 | not_rtl_bug | no_fix | final | 8 | 8 |
| B13_fsm_done_short | flag | rtl/Master_FSM.v:180 | rtl/Master_FSM.v:178 | near | no_fix | final | 8 | 8 |
| B14_fsm_nack_no_clock | corner | rtl/Master_FSM.v:156 | rtl/Master_FSM.v:96 | wrong_line | no_fix | final | 8 | 9 |
| B15_fsm_start_scl_early | corner | rtl/Master_FSM.v:99 | -:- | not_rtl_bug | no_fix | final | 8 | 8 |
| B16_fsm_reset_scl_low | reset | rtl/Master_FSM.v:56 | rtl/Master_FSM.v:56 | exact | no_fix | final | 8 | 8 |
| B17_fsm_no_load_data | guard | rtl/Master_FSM.v:131 | rtl/Slave_FSM.v:128 | wrong_file | no_fix | final | 8 | 9 |
| B18_mtx_lsb_first | pointer | rtl/Master_TX.v:25 | -:- | not_rtl_bug | no_fix | final | 8 | 8 |
| B19_mtx_addr_order | pointer | rtl/Master_TX.v:32 | rtl/Master_FSM.v:126 | wrong_file | no_fix | final | 8 | 10 |
| B20_mrx_shift_right | pointer | rtl/Master_RX.v:17 | rtl/Master_RX.v:17 | exact | fixed_golden | final | 7 | 7 |
| B21_mrx_reset_ff | reset | rtl/Master_RX.v:14 | rtl/Master_RX.v:14 | exact | fixed_pass | final | 8 | 9 |
| B22_slv_addr_bits | pointer | rtl/Slave_FSM.v:95 | rtl/Master_FSM.v:126 | wrong_file | no_fix | final | 8 | 9 |
| B23_slv_no_addr_ack | flag | rtl/Slave_FSM.v:96 | rtl/Master_FSM.v:126 | wrong_file | no_fix | final | 8 | 8 |
| B24_slv_no_write_ack | flag | rtl/Slave_FSM.v:127 | rtl/Master_FSM.v:123 | not_rtl_bug | no_fix | final | 8 | 8 |
| B25_slv_read_msb_lost | corner | rtl/Slave_FSM.v:110 | rtl/Master_RX.v:17 | wrong_file | no_fix | final | 8 | 9 |
| B26_slv_shift_on_fall | pointer | rtl/Slave_FSM.v:141 | rtl/Master_RX.v:17 | wrong_file | no_fix | final | 8 | 9 |
| B27_slv_no_rx_latch | flag | rtl/Slave_FSM.v:128 | rtl/Slave_FSM.v:128 | exact | no_fix | final | 8 | 10 |
| B28_stx_shift_right | pointer | rtl/Slave_TX.v:22 | -:- | not_rtl_bug | no_fix | final | 8 | 9 |
| B29_srx_reset_ff | reset | rtl/Slave_RX.v:14 | rtl/Slave.v:1 | wrong_file | no_fix | final | 8 | 9 |
| B30_top_sda_master_only | guard | rtl/i2c_system.v:25 | rtl/Master_FSM.v:126 | wrong_file | no_fix | final | 8 | 9 |
| E01_mtx_reset_ff | reset | - | - | equivalent_skipped | - | - | - | - |
| E02_slv_start_no_sclq | guard | - | - | equivalent_skipped | - | - | - | - |

## 해석할 때 주의

- 케이스가 30개뿐이고 버그는 한 줄 치환 단일 버그다. 비율은 통계가 아니라 이 세트에서의 관찰이다.
- 정답 줄은 패치가 적용된 줄이다. 원인과 증상이 다른 줄이면 증상 줄을 지목해도 `near`/`wrong_line`이 된다.
- 사람 TB가 쓴 신호 이름, 기대값 계산이 Agent에게 보이므로 LLM이 만든 TB의 실패에서는 결과가 다를 수 있다.
- 수정안 PASS는 "사람 TB가 못 잡는 오류가 없다"는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 본다.
- 같은 변형 세트로 TB 평가와 Agent 평가를 모두 했다. 세트에 맞춰 프롬프트를 고치면 이 수치는 낙관적이 된다.
