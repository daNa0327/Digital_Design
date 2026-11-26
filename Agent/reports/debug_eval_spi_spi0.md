# Debug Agent 평가: spi (spi0)

입력 TB: `C:/Users/Junyoung/Desktop/Verilog/Agent/dut/spi/tb/tb_spi_sc.v` (사람이 쓴 self-checking TB, 골든 PASS 검증됨). 최대 단계 8, 줄 허용 오차 2줄.
프롬프트 버전(시스템 프롬프트 해시): c6f81dc0ff61

⚠️ **중간에 멈춤**: B17_tx_posedge: quota (일일 한도 소진: You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://aistudio.google.com/docs/rate-limits. To monitor your current usage, h). 아래 수치는 끝난 케이스만의 값이다. 같은 명령에 `--resume`을 붙여 이어서 실행한다.

## 요약

평가된 케이스 17개 (사람 TB가 FAIL시키지 않아 제외 0, 동등 변형 제외 2, 미실행 13).

| 지표 | 값 |
|---|---|
| 보고서를 낸 비율 | 88% |
| 파일을 맞힘 | 59% |
| **정확한 줄** | 29% |
| **정답 줄 ±2줄 이내** | 29% |
| 평균 단계 수 (보고서를 낸 케이스) | 7.6 |
| 평균 도구 호출 수 | 5.9 |
| LLM 호출 (캐시 제외) / 캐시 | 139 / 0 |
| 형식 오류율 (단계 기준) | 7% |
| 거부된 보고서 수 | 0 |
| STOP이 아닌 이유로 끝난 응답 수 (MAX_TOKENS 등) | 21 |
| 빈 응답 재시도 (보냄 / 단계를 이어간 횟수) | 14 / 9 |
| 평탄한 도구 호출 정규화 (형식 오류였을 호출) | 2 |
| 토큰 입력 / 출력 | 678600 / 13850 |

### 도구 사용

| 도구 | 호출 수 |
|---|---|
| read_rtl | 54 |
| search_rtl | 17 |
| list_signals | 9 |
| read_tb | 8 |
| propose_fix | 7 |
| rerun_sim | 5 |
| get_log_snippet | 1 |

로그·TB·파형 조회(`get_log_snippet`, `read_tb`, `read_vcd_signal`, `sample_signals`)를 한 번이라도 쓴 케이스: 5/17. 0에 가까우면 이 평가는 실패 시뮬레이션 디버깅이 아니라 RTL 코드 리뷰 능력을 재고 있다.

### 수정안 검증 (7-5)

원본 사람 TB로 재시뮬레이션한 케이스 16개. Agent가 rerun_sim을 직접 쓴 횟수 5.

| 분류 | 개수 | 뜻 |
|---|---|---|
| fixed_golden | 2 | PASS, 골든 RTL과 같음 (원래 코드로 복원) |
| fixed_pass | 2 | PASS이지만 골든과 다름 (대안 수정이거나 TB 구멍 — diff를 직접 확인) |
| still_fail | 0 | 적용해도 FAIL |
| unverified | 0 | 적용/시뮬레이션 실패 |
| no_fix | 12 | 보고서가 수정안을 지목하지 않음 |

위치는 맞혔는데(±줄 이내) 수정안이 없거나 실패한 케이스: B02_div_count_step2, B15_tx_lsb_first

### 결과 분류

| 분류 | 개수 |
|---|---|
| exact | 5 |
| near | 0 |
| wrong_line | 5 |
| wrong_file | 2 |
| not_rtl_bug | 3 |
| no_report | 2 |

### 버그 유형별

| 유형 | 케이스 | ±줄 이내 | 정확 |
|---|---|---|---|
| corner | 5 | 1 | 1 |
| flag | 4 | 1 | 1 |
| guard | 2 | 0 | 0 |
| pointer | 5 | 2 | 2 |
| reset | 1 | 1 | 1 |

### 확신도와 정답률 (보고서를 낸 케이스)

| 확신도 | 케이스 | ±줄 이내 |
|---|---|---|
| high | 13 | 5 |
| low | 2 | 0 |

⚠️ 확신도 high인데 틀린 케이스: B01_div_period_off, B03_div_never_toggle, B06_fsm_9bits, B09_fsm_done_stuck_low, B10_fsm_done_one_cycle, B11_fsm_stuck_in_done, B13_fsm_start_ungated, B14_fsm_start_q_posedge

## 케이스별

| 버그 | 유형 | 정답 | Agent | 분류 | 수정안 | 상태 | 단계 | 호출 |
|---|---|---|---|---|---|---|---|---|
| B01_div_period_off | corner | rtl/clock_divider.v:19 | rtl/clock_divider.v:10 | wrong_line | fixed_pass | final | 4 | 4 |
| B02_div_count_step2 | corner | rtl/clock_divider.v:24 | rtl/clock_divider.v:24 | exact | no_fix | final | 8 | 10 |
| B03_div_never_toggle | corner | rtl/clock_divider.v:21 | rtl/Master_FSM.v:74 | wrong_file | no_fix | final | 8 | 8 |
| B04_div_reset_clk_high | reset | rtl/clock_divider.v:17 | rtl/clock_divider.v:17 | exact | fixed_golden | final | 8 | 10 |
| B05_fsm_7bits | pointer | rtl/Master_FSM.v:63 | - | no_report | no_fix | max_steps | 8 | 10 |
| B06_fsm_9bits | pointer | rtl/Master_FSM.v:63 | rtl/Master_FSM.v:80 | wrong_line | no_fix | final | 8 | 8 |
| B07_fsm_cnt_stuck | pointer | rtl/Master_FSM.v:70 | -:- | not_rtl_bug | no_fix | final | 8 | 9 |
| B08_fsm_busy_no_rise | flag | rtl/Master_FSM.v:51 | rtl/Master_FSM.v:51 | exact | fixed_golden | final | 6 | 7 |
| B09_fsm_done_stuck_low | flag | rtl/Master_FSM.v:66 | rtl/Master_FSM.v:74 | not_rtl_bug | no_fix | final | 8 | 10 |
| B10_fsm_done_one_cycle | flag | rtl/Master_FSM.v:78 | rtl/Master_FSM.v:74 | wrong_line | no_fix | final | 8 | 9 |
| B11_fsm_stuck_in_done | corner | rtl/Master_FSM.v:80 | rtl/Master_FSM.v:74 | wrong_line | no_fix | final | 8 | 9 |
| B12_fsm_cs_low_in_done | flag | rtl/Master_FSM.v:28 | -:- | not_rtl_bug | no_fix | final | 8 | 8 |
| B13_fsm_start_ungated | guard | rtl/Master_FSM.v:24 | rtl/Master_FSM.v:80 | wrong_line | no_fix | final | 8 | 9 |
| B14_fsm_start_q_posedge | guard | rtl/Master_FSM.v:22 | rtl/Master_TX.v:13 | wrong_file | no_fix | final | 8 | 8 |
| B15_tx_lsb_first | pointer | rtl/Master_TX.v:13 | rtl/Master_TX.v:13 | exact | no_fix | final | 8 | 8 |
| B16_tx_cnt_step2 | pointer | rtl/Master_TX.v:25 | rtl/Master_TX.v:25 | exact | fixed_pass | final | 8 | 8 |
| B17_tx_posedge | corner | rtl/Master_TX.v:15 | - | no_report | - | quota | 3 | 4 |
| B18_tx_no_cs_clear | guard | - | - | not_run | - | - | - | - |
| B19_rx_always_shift | guard | - | - | not_run | - | - | - | - |
| B20_rx_lsb_shift | pointer | - | - | not_run | - | - | - | - |
| B21_rx_reset_ff | reset | - | - | not_run | - | - | - | - |
| B22_srx_ignore_mosi | pointer | - | - | not_run | - | - | - | - |
| B23_srx_always_shift | guard | - | - | not_run | - | - | - | - |
| B24_srx_reset_ff | reset | - | - | not_run | - | - | - | - |
| B25_stx_msb_offset | pointer | - | - | not_run | - | - | - | - |
| B26_stx_no_cs_clear | guard | - | - | not_run | - | - | - | - |
| B27_master_tx_cs_tied | guard | - | - | not_run | - | - | - | - |
| B28_stx_cnt_posedge | corner | - | - | not_run | - | - | - | - |
| B29_fsm_reset_state_done | reset | - | - | not_run | - | - | - | - |
| B30_div_reset_count1 | reset | - | - | not_run | - | - | - | - |
| E01_fsm_dead_default | corner | - | - | equivalent_skipped | - | - | - | - |
| E02_fsm_load_unused | flag | - | - | equivalent_skipped | - | - | - | - |

## 해석할 때 주의

- 케이스가 17개뿐이고 버그는 한 줄 치환 단일 버그다. 비율은 통계가 아니라 이 세트에서의 관찰이다.
- 정답 줄은 패치가 적용된 줄이다. 원인과 증상이 다른 줄이면 증상 줄을 지목해도 `near`/`wrong_line`이 된다.
- 사람 TB가 쓴 신호 이름, 기대값 계산이 Agent에게 보이므로 LLM이 만든 TB의 실패에서는 결과가 다를 수 있다.
- 수정안 PASS는 "사람 TB가 못 잡는 오류가 없다"는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 본다.
- 같은 변형 세트로 TB 평가와 Agent 평가를 모두 했다. 세트에 맞춰 프롬프트를 고치면 이 수치는 낙관적이 된다.
