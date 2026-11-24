# Debug Agent 평가: sync_fifo (v0d)

입력 TB: `C:/Users/Junyoung/Desktop/Verilog/Agent/dut/sync_fifo/tb/tb_sync_fifo_sc.v` (사람이 쓴 self-checking TB, 골든 PASS 검증됨). 최대 단계 8, 줄 허용 오차 2줄.
프롬프트 버전(시스템 프롬프트 해시): a13189818b28

⚠️ **중간에 멈춤**: B10_reset_count_one: quota (일일 호출 상한(450회)에 도달함 - 태평양 시간 자정(한국 시간 오후 4~5시)에 초기화). 아래 수치는 끝난 케이스만의 값이다. 같은 명령에 `--resume`을 붙여 이어서 실행한다.

## 요약

평가된 케이스 10개 (사람 TB가 FAIL시키지 않아 제외 0, 동등 변형 제외 2, 미실행 7).

| 지표 | 값 |
|---|---|
| 보고서를 낸 비율 | 90% |
| 파일을 맞힘 | 90% |
| **정확한 줄** | 90% |
| **정답 줄 ±2줄 이내** | 90% |
| 평균 단계 수 (보고서를 낸 케이스) | 6.1 |
| 평균 도구 호출 수 | 4.7 |
| LLM 호출 (캐시 제외) / 캐시 | 60 / 0 |
| 형식 오류율 (단계 기준) | 3% |
| 거부된 보고서 수 | 0 |
| STOP이 아닌 이유로 끝난 응답 수 (MAX_TOKENS 등) | 11 |
| 빈 응답 재시도 (보냄 / 단계를 이어간 횟수) | 2 / 1 |
| 평탄한 도구 호출 정규화 (형식 오류였을 호출) | 0 |
| 토큰 입력 / 출력 | 259793 / 6620 |

### 결과 분류

| 분류 | 개수 |
|---|---|
| exact | 9 |
| near | 0 |
| wrong_line | 0 |
| wrong_file | 0 |
| not_rtl_bug | 0 |
| no_report | 1 |

### 버그 유형별

| 유형 | 케이스 | ±줄 이내 | 정확 |
|---|---|---|---|
| flag | 3 | 3 | 3 |
| pointer | 6 | 6 | 6 |
| reset | 1 | 0 | 0 |

### 확신도와 정답률 (보고서를 낸 케이스)

| 확신도 | 케이스 | ±줄 이내 |
|---|---|---|
| high | 9 | 9 |

## 케이스별

| 버그 | 유형 | 정답 | Agent | 분류 | 상태 | 단계 | 호출 |
|---|---|---|---|---|---|---|---|
| B01_read_ptr_no_inc | pointer | rtl/fifo_ctrl.v:33 | rtl/fifo_ctrl.v:33 | exact | final | 5 | 5 |
| B02_write_ptr_no_inc | pointer | rtl/fifo_ctrl.v:40 | rtl/fifo_ctrl.v:40 | exact | final | 7 | 7 |
| B03_both_rd_ptr_stuck | pointer | rtl/fifo_ctrl.v:49 | rtl/fifo_ctrl.v:49 | exact | final | 6 | 6 |
| B04_both_wr_ptr_stuck | pointer | rtl/fifo_ctrl.v:48 | rtl/fifo_ctrl.v:48 | exact | final | 5 | 5 |
| B05_read_count_dec2 | pointer | rtl/fifo_ctrl.v:34 | rtl/fifo_ctrl.v:34 | exact | final | 7 | 7 |
| B06_write_count_no_inc | pointer | rtl/fifo_ctrl.v:41 | rtl/fifo_ctrl.v:41 | exact | final | 7 | 8 |
| B07_full_at_7 | flag | rtl/fifo_ctrl.v:17 | rtl/fifo_ctrl.v:17 | exact | final | 5 | 5 |
| B08_empty_at_1 | flag | rtl/fifo_ctrl.v:16 | rtl/fifo_ctrl.v:16 | exact | final | 6 | 7 |
| B09_full_never | flag | rtl/fifo_ctrl.v:17 | rtl/fifo_ctrl.v:17 | exact | final | 7 | 7 |
| B10_reset_count_one | reset | rtl/fifo_ctrl.v:23 | - | no_report | quota | 3 | 3 |
| B11_reset_rd_ptr_one | reset | - | - | not_run | - | - | - |
| B12_mem_read_addr_wr | memory | - | - | not_run | - | - | - |
| B13_mem_write_data_plus1 | memory | - | - | not_run | - | - | - |
| B14_mem_read_ungated | memory | - | - | not_run | - | - | - |
| B15_no_full_guard | guard | - | - | not_run | - | - | - |
| B16_no_empty_guard | guard | - | - | not_run | - | - | - |
| B17_both_ignored_at_7 | corner | - | - | not_run | - | - | - |
| E01_dead_full_branch | pointer | - | - | equivalent_skipped | - | - | - |
| E02_dead_empty_branch | pointer | - | - | equivalent_skipped | - | - | - |

## 해석할 때 주의

- 케이스가 10개뿐이고 버그는 한 줄 치환 단일 버그다. 비율은 통계가 아니라 이 세트에서의 관찰이다.
- 정답 줄은 패치가 적용된 줄이다. 원인과 증상이 다른 줄이면 증상 줄을 지목해도 `near`/`wrong_line`이 된다.
- 사람 TB가 쓴 신호 이름, 기대값 계산이 Agent에게 보이므로 LLM이 만든 TB의 실패에서는 결과가 다를 수 있다.
- 같은 변형 세트로 TB 평가와 Agent 평가를 모두 했다. 세트에 맞춰 프롬프트를 고치면 이 수치는 낙관적이 된다.
