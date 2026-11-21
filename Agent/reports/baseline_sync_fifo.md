# Baseline: TB-only 평가: sync_fifo

LLM/Agent 없이 결정적 구간(`XsimSim` → `analyze`)과 self-checking TB만으로 정답을 아는 버그를 얼마나 잡는지 잰 기준선이다. 이후 Agent의 성능은 이 기준선과 비교한다.

## 골든

- status: `PASS`, tb_verdict: `PASS`

## 요약

| 항목 | 값 |
|---|---|
| 변형 수 (전체) | 19 |
| 점수 대상 (동등/invalid 제외) | 17 |
| detected | 17 |
| survived (TB가 못 잡음) | 0 |
| invalid (빌드 실패/타임아웃) | 0 |
| 동등 변형 (정상 생존) | 2 |
| 동등 변형이 잡힘 (메타데이터 오류) | 0 |
| **mutation score** | **100.0%** |

## 유형별

| 유형 | detected | survived |
|---|---|---|
| pointer | 6 | 0 |
| flag | 3 | 0 |
| reset | 2 | 0 |
| memory | 3 | 0 |
| guard | 2 | 0 |
| corner | 1 | 0 |

## 탐지 시점

첫 불일치 시각: 최소 27 ns, 중앙값 157 ns, 최대 417 ns (대상 17개). 늦게 잡히는 변형일수록 특정 상황을 만들어야 드러나는 버그다.

## 변형별 결과

| id | 유형 | 패치 줄 | 결과 | 첫 불일치 | 불일치 수 | 실행 |
|---|---|---|---|---|---|---|
| B01_read_ptr_no_inc | pointer | 33 | detected | `data_out` @ 167 ns | 3553/4099 | 10.6s |
| B02_write_ptr_no_inc | pointer | 40 | detected | `data_out` @ 157 ns | 3774/4099 | 11.9s |
| B03_both_rd_ptr_stuck | pointer | 49 | detected | `data_out` @ 297 ns | 3560/4099 | 13.3s |
| B04_both_wr_ptr_stuck | pointer | 48 | detected | `data_out` @ 397 ns | 3729/4099 | 12.0s |
| B05_read_count_dec2 | pointer | 34 | detected | `empty` @ 187 ns | 4693/4099 | 10.4s |
| B06_write_count_no_inc | pointer | 41 | detected | `empty` @ 37 ns | 8154/4099 | 11.0s |
| B07_full_at_7 | flag | 17 | detected | `full` @ 97 ns | 1568/4099 | 11.7s |
| B08_empty_at_1 | flag | 16 | detected | `empty` @ 27 ns | 2505/4099 | 11.7s |
| B09_full_never | flag | 17 | detected | `full` @ 107 ns | 1643/4099 | 11.1s |
| B10_reset_count_one | reset | 23 | detected | `empty` @ 27 ns | 4062/4099 | 11.0s |
| B11_reset_rd_ptr_one | reset | 22 | detected | `data_out` @ 157 ns | 4074/4099 | 11.0s |
| B12_mem_read_addr_wr | memory | 20 | detected | `data_out` @ 167 ns | 3318/4099 | 11.8s |
| B13_mem_write_data_plus1 | memory | 17 | detected | `data_out` @ 157 ns | 4086/4099 | 9.9s |
| B14_mem_read_ungated | memory | 19 | detected | `data_out` @ 237 ns | 2285/4099 | 10.4s |
| B15_no_full_guard | guard | 20 | detected | `data_out` @ 157 ns | 525/4099 | 10.8s |
| B16_no_empty_guard | guard | 21 | detected | `data_out` @ 237 ns | 812/4099 | 9.9s |
| B17_both_ignored_at_7 | corner | 47 | detected | `data_out` @ 417 ns | 1146/4099 | 10.6s |
| E01_dead_full_branch | pointer | 58 | equivalent (정상 생존) | - | 0/4099 | 11.6s |
| E02_dead_empty_branch | pointer | 54 | equivalent (정상 생존) | - | 0/4099 | 10.8s |

## 해석 시 주의

- 점수 100%는 "이 변형 세트를 TB가 모두 잡는다"는 뜻이지 TB가 완전하다는 뜻이 아니다. 변형은 한 줄 치환 단일 버그뿐이다.
- 동등 변형은 코드상 도달 불가능한 분기를 바꾼 것으로, 코드 읽기와 두 시뮬레이터에서의 PASS로 판단했으며 형식 검증을 한 것은 아니다.
- 랜덤 구간은 고정 seed라 결정적이다. 늦게 잡히는 변형은 seed나 길이를 바꾸면 결과가 달라질 수 있다.
