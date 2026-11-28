# 수정안 사후 검증: sync_fifo (dbgeval_v0f_20261128_184222)

Agent 보고서가 지목한 수정안을 버그 있는 RTL에 적용해 원본 사람 TB로 재시뮬레이션했다. PASS는 TB가 못 잡는 오류가 없다는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 확인한다.

| 분류 | 개수 |
|---|---|
| fixed_golden | 14 |
| fixed_pass | 1 |
| still_fail | 0 |
| unverified | 0 |
| no_fix | 2 |

| 버그 | 위치 분류 | 수정안 | 제안별 (id: 상태, 골든과 같음) |
|---|---|---|---|
| B01_read_ptr_no_inc | exact | fixed_golden | 1: PASS, 골든 |
| B02_write_ptr_no_inc | exact | fixed_golden | 1: PASS, 골든 |
| B03_both_rd_ptr_stuck | exact | fixed_golden | 1: PASS, 골든 |
| B04_both_wr_ptr_stuck | exact | fixed_pass | 1: PASS |
| B05_read_count_dec2 | exact | fixed_golden | 1: PASS, 골든 |
| B06_write_count_no_inc | exact | fixed_golden | 1: PASS, 골든 |
| B07_full_at_7 | exact | fixed_golden | 1: PASS, 골든 |
| B08_empty_at_1 | exact | fixed_golden | 1: PASS, 골든 |
| B09_full_never | exact | fixed_golden | 1: PASS, 골든 |
| B10_reset_count_one | exact | fixed_golden | 1: PASS, 골든 |
| B11_reset_rd_ptr_one | exact | fixed_golden | 1: PASS, 골든 |
| B12_mem_read_addr_wr | exact | fixed_golden | 1: PASS, 골든 |
| B13_mem_write_data_plus1 | exact | fixed_golden | 1: PASS, 골든 |
| B14_mem_read_ungated | no_report | no_fix | - |
| B15_no_full_guard | not_rtl_bug | no_fix | - |
| B16_no_empty_guard | exact | fixed_golden | 1: PASS, 골든 |
| B17_both_ignored_at_7 | exact | fixed_golden | 1: PASS, 골든 |
