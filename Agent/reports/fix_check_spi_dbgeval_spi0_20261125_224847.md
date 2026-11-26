# 수정안 사후 검증: spi (dbgeval_spi0_20261125_224847)

Agent 보고서가 지목한 수정안을 버그 있는 RTL에 적용해 원본 사람 TB로 재시뮬레이션했다. PASS는 TB가 못 잡는 오류가 없다는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 확인한다.

| 분류 | 개수 |
|---|---|
| fixed_golden | 9 |
| fixed_pass | 4 |
| still_fail | 0 |
| unverified | 0 |
| no_fix | 17 |

| 버그 | 위치 분류 | 수정안 | 제안별 (id: 상태, 골든과 같음) |
|---|---|---|---|
| B01_div_period_off | wrong_line | fixed_pass | 1: PASS |
| B02_div_count_step2 | exact | no_fix | - |
| B03_div_never_toggle | wrong_file | no_fix | - |
| B04_div_reset_clk_high | exact | fixed_golden | 1: PASS, 골든 |
| B05_fsm_7bits | no_report | no_fix | - |
| B06_fsm_9bits | wrong_line | no_fix | - |
| B07_fsm_cnt_stuck | not_rtl_bug | no_fix | - |
| B08_fsm_busy_no_rise | exact | fixed_golden | 1: PASS, 골든 |
| B09_fsm_done_stuck_low | not_rtl_bug | no_fix | - |
| B10_fsm_done_one_cycle | wrong_line | no_fix | - |
| B11_fsm_stuck_in_done | wrong_line | no_fix | - |
| B12_fsm_cs_low_in_done | not_rtl_bug | no_fix | - |
| B13_fsm_start_ungated | wrong_line | no_fix | - |
| B14_fsm_start_q_posedge | wrong_file | no_fix | - |
| B15_tx_lsb_first | exact | no_fix | - |
| B16_tx_cnt_step2 | exact | fixed_pass | 1: PASS |
| B17_tx_posedge | exact | fixed_golden | 1: PASS, 골든 |
| B18_tx_no_cs_clear | exact | no_fix | - |
| B19_rx_always_shift | not_rtl_bug | no_fix | - |
| B20_rx_lsb_shift | exact | fixed_golden | 1: PASS, 골든 |
| B21_rx_reset_ff | exact | fixed_pass | 1: PASS |
| B22_srx_ignore_mosi | exact | fixed_golden | 1: PASS, 골든 |
| B23_srx_always_shift | exact | fixed_golden | 1: PASS, 골든 |
| B24_srx_reset_ff | exact | fixed_pass | 1: PASS |
| B25_stx_msb_offset | exact | no_fix | - |
| B26_stx_no_cs_clear | wrong_line | no_fix | - |
| B27_master_tx_cs_tied | exact | fixed_golden | 1: PASS, 골든 |
| B28_stx_cnt_posedge | exact | fixed_golden | 1: PASS, 골든 |
| B29_fsm_reset_state_done | exact | fixed_golden | 1: PASS, 골든 |
| B30_div_reset_count1 | no_report | no_fix | - |
