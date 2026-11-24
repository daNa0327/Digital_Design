# Debug Agent 평가: sync_fifo (v0c)

입력 TB: `C:/Users/Junyoung/Desktop/Verilog/Agent/dut/sync_fifo/tb/tb_sync_fifo_sc.v` (사람이 쓴 self-checking TB, 골든 PASS 검증됨). 최대 단계 8, 줄 허용 오차 2줄.
프롬프트 버전(시스템 프롬프트 해시): a13189818b28

## 요약

평가된 케이스 17개 (사람 TB가 FAIL시키지 않아 제외 0, 동등 변형 제외 2, 미실행 0).

| 지표 | 값 |
|---|---|
| 보고서를 낸 비율 | 100% |
| 파일을 맞힘 | 82% |
| **정확한 줄** | 76% |
| **정답 줄 ±2줄 이내** | 82% |
| 평균 단계 수 (보고서를 낸 케이스) | 6.9 |
| 평균 도구 호출 수 | 5.6 |
| LLM 호출 (캐시 제외) / 캐시 | 119 / 0 |
| 형식 오류율 (단계 기준) | 4% |
| 거부된 보고서 수 | 0 |
| STOP이 아닌 이유로 끝난 응답 수 (MAX_TOKENS 등) | 8 |
| 빈 응답 재시도 (보냄 / 단계를 이어간 횟수) | 2 / 2 |
| 토큰 입력 / 출력 | 553838 / 14788 |

### 결과 분류

| 분류 | 개수 |
|---|---|
| exact | 13 |
| near | 1 |
| wrong_line | 0 |
| wrong_file | 2 |
| not_rtl_bug | 1 |
| no_report | 0 |

### 버그 유형별

| 유형 | 케이스 | ±줄 이내 | 정확 |
|---|---|---|---|
| corner | 1 | 1 | 1 |
| flag | 3 | 3 | 3 |
| guard | 2 | 0 | 0 |
| memory | 3 | 2 | 2 |
| pointer | 6 | 6 | 5 |
| reset | 2 | 2 | 2 |

### 확신도와 정답률 (보고서를 낸 케이스)

| 확신도 | 케이스 | ±줄 이내 |
|---|---|---|
| high | 16 | 14 |
| medium | 1 | 0 |

⚠️ 확신도 high인데 틀린 케이스: B14_mem_read_ungated, B16_no_empty_guard

## 케이스별

| 버그 | 유형 | 정답 | Agent | 분류 | 상태 | 단계 | 호출 |
|---|---|---|---|---|---|---|---|
| B01_read_ptr_no_inc | pointer | rtl/fifo_ctrl.v:33 | rtl/fifo_ctrl.v:33 | exact | final | 7 | 7 |
| B02_write_ptr_no_inc | pointer | rtl/fifo_ctrl.v:40 | rtl/fifo_ctrl.v:40 | exact | final | 8 | 8 |
| B03_both_rd_ptr_stuck | pointer | rtl/fifo_ctrl.v:49 | rtl/fifo_ctrl.v:47 | near | final | 7 | 7 |
| B04_both_wr_ptr_stuck | pointer | rtl/fifo_ctrl.v:48 | rtl/fifo_ctrl.v:48 | exact | final | 6 | 6 |
| B05_read_count_dec2 | pointer | rtl/fifo_ctrl.v:34 | rtl/fifo_ctrl.v:34 | exact | final | 7 | 7 |
| B06_write_count_no_inc | pointer | rtl/fifo_ctrl.v:41 | rtl/fifo_ctrl.v:41 | exact | final | 6 | 6 |
| B07_full_at_7 | flag | rtl/fifo_ctrl.v:17 | rtl/fifo_ctrl.v:17 | exact | final | 8 | 8 |
| B08_empty_at_1 | flag | rtl/fifo_ctrl.v:16 | rtl/fifo_ctrl.v:16 | exact | final | 8 | 8 |
| B09_full_never | flag | rtl/fifo_ctrl.v:17 | rtl/fifo_ctrl.v:17 | exact | final | 5 | 5 |
| B10_reset_count_one | reset | rtl/fifo_ctrl.v:23 | rtl/fifo_ctrl.v:23 | exact | final | 5 | 5 |
| B11_reset_rd_ptr_one | reset | rtl/fifo_ctrl.v:22 | rtl/fifo_ctrl.v:22 | exact | final | 8 | 9 |
| B12_mem_read_addr_wr | memory | rtl/fifo_mem.v:20 | rtl/fifo_mem.v:20 | exact | final | 8 | 8 |
| B13_mem_write_data_plus1 | memory | rtl/fifo_mem.v:17 | rtl/fifo_mem.v:17 | exact | final | 6 | 6 |
| B14_mem_read_ungated | memory | rtl/fifo_mem.v:19 | rtl/fifo_ctrl.v:49 | wrong_file | final | 6 | 7 |
| B15_no_full_guard | guard | rtl/sync_fifo.v:20 | -:- | not_rtl_bug | final | 8 | 8 |
| B16_no_empty_guard | guard | rtl/sync_fifo.v:21 | rtl/fifo_ctrl.v:47 | wrong_file | final | 8 | 8 |
| B17_both_ignored_at_7 | corner | rtl/fifo_ctrl.v:47 | rtl/fifo_ctrl.v:47 | exact | final | 6 | 6 |
| E01_dead_full_branch | pointer | - | - | equivalent_skipped | - | - | - |
| E02_dead_empty_branch | pointer | - | - | equivalent_skipped | - | - | - |

## 해석할 때 주의

- 케이스가 17개뿐이고 버그는 한 줄 치환 단일 버그다. 비율은 통계가 아니라 이 세트에서의 관찰이다.
- 정답 줄은 패치가 적용된 줄이다. 원인과 증상이 다른 줄이면 증상 줄을 지목해도 `near`/`wrong_line`이 된다.
- 사람 TB가 쓴 신호 이름, 기대값 계산이 Agent에게 보이므로 LLM이 만든 TB의 실패에서는 결과가 다를 수 있다.
- 같은 변형 세트로 TB 평가와 Agent 평가를 모두 했다. 세트에 맞춰 프롬프트를 고치면 이 수치는 낙관적이 된다.
