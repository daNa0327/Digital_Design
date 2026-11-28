# Debug Agent 평가: sync_fifo (v0f)

입력 TB: `C:/Users/Junyoung/Desktop/Verilog/Agent/dut/sync_fifo/tb/tb_sync_fifo_sc.v` (사람이 쓴 self-checking TB, 골든 PASS 검증됨). 최대 단계 10, 줄 허용 오차 2줄.
프롬프트 버전(시스템 프롬프트 해시): c6f81dc0ff61

## 요약

평가된 케이스 17개 (사람 TB가 FAIL시키지 않아 제외 0, 동등 변형 제외 2, 미실행 0).

| 지표 | 값 |
|---|---|
| 보고서를 낸 비율 | 94% |
| 파일을 맞힘 | 88% |
| **정확한 줄** | 88% |
| **정답 줄 ±2줄 이내** | 88% |
| 평균 단계 수 (보고서를 낸 케이스) | 7.8 |
| 평균 도구 호출 수 | 6.5 |
| LLM 호출 (캐시 제외) / 캐시 | 153 / 0 |
| 형식 오류율 (단계 기준) | 6% |
| 거부된 보고서 수 | 1 |
| STOP이 아닌 이유로 끝난 응답 수 (MAX_TOKENS 등) | 30 |
| 빈 응답 재시도 (보냄 / 단계를 이어간 횟수) | 17 / 11 |
| 평탄한 도구 호출 정규화 (형식 오류였을 호출) | 2 |
| 토큰 입력 / 출력 | 748804 / 13876 |

### 도구 사용

| 도구 | 호출 수 |
|---|---|
| read_rtl | 59 |
| propose_fix | 22 |
| rerun_sim | 17 |
| search_rtl | 6 |
| read_tb | 4 |
| list_signals | 3 |

로그·TB·파형 조회(`get_log_snippet`, `read_tb`, `read_vcd_signal`, `sample_signals`)를 한 번이라도 쓴 케이스: 1/17. 0에 가까우면 이 평가는 실패 시뮬레이션 디버깅이 아니라 RTL 코드 리뷰 능력을 재고 있다.

### 수정안 검증 (7-5)

원본 사람 TB로 재시뮬레이션한 케이스 17개. Agent가 rerun_sim을 직접 쓴 횟수 17.

| 분류 | 개수 | 뜻 |
|---|---|---|
| fixed_golden | 14 | PASS, 골든 RTL과 같음 (원래 코드로 복원) |
| fixed_pass | 1 | PASS이지만 골든과 다름 (대안 수정이거나 TB 구멍 — diff를 직접 확인) |
| still_fail | 0 | 적용해도 FAIL |
| unverified | 0 | 적용/시뮬레이션 실패 |
| no_fix | 2 | 보고서가 수정안을 지목하지 않음 |

위치는 맞혔는데(±줄 이내) 수정안이 없거나 실패한 케이스: 없음

### 결과 분류

| 분류 | 개수 |
|---|---|
| exact | 15 |
| near | 0 |
| wrong_line | 0 |
| wrong_file | 0 |
| not_rtl_bug | 1 |
| no_report | 1 |

### 버그 유형별

| 유형 | 케이스 | ±줄 이내 | 정확 |
|---|---|---|---|
| corner | 1 | 1 | 1 |
| flag | 3 | 3 | 3 |
| guard | 2 | 1 | 1 |
| memory | 3 | 2 | 2 |
| pointer | 6 | 6 | 6 |
| reset | 2 | 2 | 2 |

### 확신도와 정답률 (보고서를 낸 케이스)

| 확신도 | 케이스 | ±줄 이내 |
|---|---|---|
| high | 15 | 15 |
| low | 1 | 0 |

## 케이스별

| 버그 | 유형 | 정답 | Agent | 분류 | 수정안 | 상태 | 단계 | 호출 |
|---|---|---|---|---|---|---|---|---|
| B01_read_ptr_no_inc | pointer | rtl/fifo_ctrl.v:33 | rtl/fifo_ctrl.v:33 | exact | fixed_golden | final | 9 | 10 |
| B02_write_ptr_no_inc | pointer | rtl/fifo_ctrl.v:40 | rtl/fifo_ctrl.v:40 | exact | fixed_golden | final | 8 | 10 |
| B03_both_rd_ptr_stuck | pointer | rtl/fifo_ctrl.v:49 | rtl/fifo_ctrl.v:49 | exact | fixed_golden | final | 7 | 7 |
| B04_both_wr_ptr_stuck | pointer | rtl/fifo_ctrl.v:48 | rtl/fifo_ctrl.v:48 | exact | fixed_pass | final | 9 | 10 |
| B05_read_count_dec2 | pointer | rtl/fifo_ctrl.v:34 | rtl/fifo_ctrl.v:34 | exact | fixed_golden | final | 5 | 5 |
| B06_write_count_no_inc | pointer | rtl/fifo_ctrl.v:41 | rtl/fifo_ctrl.v:41 | exact | fixed_golden | final | 6 | 7 |
| B07_full_at_7 | flag | rtl/fifo_ctrl.v:17 | rtl/fifo_ctrl.v:17 | exact | fixed_golden | final | 6 | 6 |
| B08_empty_at_1 | flag | rtl/fifo_ctrl.v:16 | rtl/fifo_ctrl.v:16 | exact | fixed_golden | final | 7 | 7 |
| B09_full_never | flag | rtl/fifo_ctrl.v:17 | rtl/fifo_ctrl.v:17 | exact | fixed_golden | final | 8 | 8 |
| B10_reset_count_one | reset | rtl/fifo_ctrl.v:23 | rtl/fifo_ctrl.v:23 | exact | fixed_golden | final | 8 | 11 |
| B11_reset_rd_ptr_one | reset | rtl/fifo_ctrl.v:22 | rtl/fifo_ctrl.v:22 | exact | fixed_golden | final | 8 | 9 |
| B12_mem_read_addr_wr | memory | rtl/fifo_mem.v:20 | rtl/fifo_mem.v:20 | exact | fixed_golden | final | 8 | 8 |
| B13_mem_write_data_plus1 | memory | rtl/fifo_mem.v:17 | rtl/fifo_mem.v:17 | exact | fixed_golden | final | 7 | 7 |
| B14_mem_read_ungated | memory | rtl/fifo_mem.v:19 | - | no_report | no_fix | max_steps | 11 | 12 |
| B15_no_full_guard | guard | rtl/sync_fifo.v:20 | rtl/fifo_mem.v:15 | not_rtl_bug | no_fix | final | 13 | 18 |
| B16_no_empty_guard | guard | rtl/sync_fifo.v:21 | rtl/sync_fifo.v:21 | exact | fixed_golden | final | 8 | 10 |
| B17_both_ignored_at_7 | corner | rtl/fifo_ctrl.v:47 | rtl/fifo_ctrl.v:47 | exact | fixed_golden | final | 8 | 8 |
| E01_dead_full_branch | pointer | - | - | equivalent_skipped | - | - | - | - |
| E02_dead_empty_branch | pointer | - | - | equivalent_skipped | - | - | - | - |

## 해석할 때 주의

- 케이스가 17개뿐이고 버그는 한 줄 치환 단일 버그다. 비율은 통계가 아니라 이 세트에서의 관찰이다.
- 정답 줄은 패치가 적용된 줄이다. 원인과 증상이 다른 줄이면 증상 줄을 지목해도 `near`/`wrong_line`이 된다.
- 사람 TB가 쓴 신호 이름, 기대값 계산이 Agent에게 보이므로 LLM이 만든 TB의 실패에서는 결과가 다를 수 있다.
- 수정안 PASS는 "사람 TB가 못 잡는 오류가 없다"는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 본다.
- 같은 변형 세트로 TB 평가와 Agent 평가를 모두 했다. 세트에 맞춰 프롬프트를 고치면 이 수치는 낙관적이 된다.
