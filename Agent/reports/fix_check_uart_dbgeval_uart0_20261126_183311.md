# 수정안 사후 검증: uart (dbgeval_uart0_20261126_183311)

Agent 보고서가 지목한 수정안을 버그 있는 RTL에 적용해 원본 사람 TB로 재시뮬레이션했다. PASS는 TB가 못 잡는 오류가 없다는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 확인한다.

| 분류 | 개수 |
|---|---|
| fixed_golden | 17 |
| fixed_pass | 1 |
| still_fail | 1 |
| unverified | 0 |
| no_fix | 11 |

| 버그 | 위치 분류 | 수정안 | 제안별 (id: 상태, 골든과 같음) |
|---|---|---|---|
| B01_baud_period_short | exact | fixed_golden | 1: PASS, 골든 |
| B02_baud_wrap_one | wrong_file | no_fix | - |
| B03_baud_reset_count | wrong_file | no_fix | - |
| B04_baud_tick_stuck | wrong_line | no_fix | - |
| B05_tx_msb_first | wrong_line | no_fix | - |
| B06_tx_7bits | exact | fixed_golden | 1: PASS, 골든 |
| B07_tx_bitidx_no_clear | exact | fixed_golden | 1: PASS, 골든 |
| B08_tx_start_bit_high | not_rtl_bug | no_fix | - |
| B09_tx_stop_bit_low | exact | fixed_golden | 1: PASS, 골든 |
| B10_tx_reset_low | no_report | no_fix | - |
| B11_tx_busy_reset_high | exact | no_fix | - |
| B12_tx_busy_late | exact | fixed_golden | 1: PASS, 골든 |
| B13_tx_busy_early_fall | exact | fixed_golden | 1: PASS, 골든 |
| B14_tx_no_latch | exact | fixed_golden | 1: PASS, 골든 |
| B15_tx_ignore_tick | wrong_line | no_fix | - |
| B16_tx_auto_restart | no_report | no_fix | - |
| B17_tx_skip_stop | exact | fixed_golden | 1: PASS, 골든 |
| B18_rx_sample_edge | exact | fixed_golden | 1: PASS, 골든 |
| B19_rx_msb_first | exact | fixed_golden | 1: PASS, 골든 |
| B20_rx_7bits | exact | fixed_golden | 1: PASS, 골든 |
| B21_rx_bitidx_no_clear | exact | fixed_golden | 1: PASS, 골든 |
| B22_rx_no_stop_check | wrong_line | no_fix | - |
| B23_rx_start_on_high | exact | fixed_golden | 1: PASS, 골든 |
| B24_rx_valid_stuck | exact | fixed_golden | 1: PASS, 골든 |
| B25_rx_valid_reset_high | exact | fixed_golden | 1: PASS, 골든 |
| B26_rx_data_reset_ff | exact | fixed_pass | 1: PASS |
| B27_rx_count_no_clear | exact | fixed_golden | 1: PASS, 골든 |
| B28_rx_stop_half | exact | fixed_golden | 1: PASS, 골든 |
| B29_rx_data_period_short | wrong_line | still_fail | 1: FAIL |
| B30_top_tick_tied | no_report | no_fix | - |
