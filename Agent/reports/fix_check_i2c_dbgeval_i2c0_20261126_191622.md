# 수정안 사후 검증: i2c (dbgeval_i2c0_20261126_191622)

Agent 보고서가 지목한 수정안을 버그 있는 RTL에 적용해 원본 사람 TB로 재시뮬레이션했다. PASS는 TB가 못 잡는 오류가 없다는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 확인한다.

| 분류 | 개수 |
|---|---|
| fixed_golden | 2 |
| fixed_pass | 1 |
| still_fail | 0 |
| unverified | 0 |
| no_fix | 27 |

| 버그 | 위치 분류 | 수정안 | 제안별 (id: 상태, 골든과 같음) |
|---|---|---|---|
| B01_div_period_short | exact | no_fix | - |
| B02_div_count_step2 | exact | fixed_golden | 1: PASS, 골든 |
| B03_div_tick_stuck | wrong_file | no_fix | - |
| B04_fsm_no_start_cond | not_rtl_bug | no_fix | - |
| B05_fsm_tx_inverted | not_rtl_bug | no_fix | - |
| B06_fsm_7bits_tx | not_rtl_bug | no_fix | - |
| B07_fsm_7bits_rx | wrong_line | no_fix | - |
| B08_fsm_ignore_nack | exact | no_fix | - |
| B09_fsm_ack_error_sticky | wrong_line | no_fix | - |
| B10_fsm_nack_continue | not_rtl_bug | no_fix | - |
| B11_fsm_rw_swapped | not_rtl_bug | no_fix | - |
| B12_fsm_no_stop_cond | not_rtl_bug | no_fix | - |
| B13_fsm_done_short | near | no_fix | - |
| B14_fsm_nack_no_clock | wrong_line | no_fix | - |
| B15_fsm_start_scl_early | not_rtl_bug | no_fix | - |
| B16_fsm_reset_scl_low | exact | no_fix | - |
| B17_fsm_no_load_data | wrong_file | no_fix | - |
| B18_mtx_lsb_first | not_rtl_bug | no_fix | - |
| B19_mtx_addr_order | wrong_file | no_fix | - |
| B20_mrx_shift_right | exact | fixed_golden | 1: PASS, 골든 |
| B21_mrx_reset_ff | exact | fixed_pass | 1: PASS |
| B22_slv_addr_bits | wrong_file | no_fix | - |
| B23_slv_no_addr_ack | wrong_file | no_fix | - |
| B24_slv_no_write_ack | not_rtl_bug | no_fix | - |
| B25_slv_read_msb_lost | wrong_file | no_fix | - |
| B26_slv_shift_on_fall | wrong_file | no_fix | - |
| B27_slv_no_rx_latch | exact | no_fix | - |
| B28_stx_shift_right | not_rtl_bug | no_fix | - |
| B29_srx_reset_ff | wrong_file | no_fix | - |
| B30_top_sda_master_only | wrong_file | no_fix | - |
