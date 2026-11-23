# TB 비교: human vs llm

- **llm**: `runs/tb/sync_fifo_llm_gated.v` (top `tb_sync_fifo`, sha256 `469112bec769`)

## 골든 (정상 RTL에서 PASS해야 함)

| TB | status | tb_verdict |
|---|---|---|
| human | `PASS` | `PASS` |
| llm | `PASS` | `PASS` |

## 요약

| 항목 | human | llm |
|---|---|---|
| 점수 대상 변형 | 17 | 17 |
| detected | 17 | 17 |
| survived | 0 | 0 |
| invalid | 0 | 0 |
| **mutation score** | **100.0%** | **100.0%** |

## 차이

- human만 잡음: 없음
- llm만 잡음: 없음
- 둘 다 못 잡음: 없음
- 둘 다 잡음: 17개

## 변형별

| id | 유형 | human | llm | human 첫 불일치 | llm 첫 불일치 | 비고 |
|---|---|---|---|---|---|---|
| B01_read_ptr_no_inc | pointer | detected | detected | `data_out` @ 167 ns | `data_out` @ - |  |
| B02_write_ptr_no_inc | pointer | detected | detected | `data_out` @ 157 ns | `data_out` @ - |  |
| B03_both_rd_ptr_stuck | pointer | detected | detected | `data_out` @ 297 ns | `data_out` @ - |  |
| B04_both_wr_ptr_stuck | pointer | detected | detected | `data_out` @ 397 ns | `data_out` @ - |  |
| B05_read_count_dec2 | pointer | detected | detected | `empty` @ 187 ns | `empty` @ - |  |
| B06_write_count_no_inc | pointer | detected | detected | `empty` @ 37 ns | `empty` @ - |  |
| B07_full_at_7 | flag | detected | detected | `full` @ 97 ns | `full` @ - |  |
| B08_empty_at_1 | flag | detected | detected | `empty` @ 27 ns | `empty` @ - |  |
| B09_full_never | flag | detected | detected | `full` @ 107 ns | `full` @ - |  |
| B10_reset_count_one | reset | detected | detected | `empty` @ 27 ns | `empty` @ - |  |
| B11_reset_rd_ptr_one | reset | detected | detected | `data_out` @ 157 ns | `data_out` @ - |  |
| B12_mem_read_addr_wr | memory | detected | detected | `data_out` @ 167 ns | `data_out` @ - |  |
| B13_mem_write_data_plus1 | memory | detected | detected | `data_out` @ 157 ns | `data_out` @ - |  |
| B14_mem_read_ungated | memory | detected | detected | `data_out` @ 237 ns | `data_out` @ - |  |
| B15_no_full_guard | guard | detected | detected | `data_out` @ 157 ns | `data_out` @ - |  |
| B16_no_empty_guard | guard | detected | detected | `data_out` @ 237 ns | `data_out` @ - |  |
| B17_both_ignored_at_7 | corner | detected | detected | `data_out` @ 417 ns | `data_out` @ - |  |
| E01_dead_full_branch | pointer | equivalent_ok | equivalent_ok | - | - |  |
| E02_dead_empty_branch | pointer | equivalent_ok | equivalent_ok | - | - |  |

## 해석 시 주의

- 변형 세트는 한 줄 치환 단일 버그 19개다. 점수가 같아도 TB가 같은 품질이라는 뜻은 아니다.
- LLM TB는 RTL 소스를 보고 만들었다. 변형 세트(버그 목록)는 보여주지 않았지만, 참조 모델이 RTL 구조를 따랐을 수 있다.
- LLM 출력은 비결정적이다. 이 비교는 한 번의 생성 결과이며(온도 0, 캐시됨), 다른 생성에서는 점수가 달라질 수 있다.
- 골든 PASS는 필수 조건이다. 정상 RTL에서 FAIL하는 TB는 점수와 무관하게 쓸 수 없다.
