# sync_fifo 명세 (TB Generator 입력용)

이 파일은 **동작 명세만** 담는다. 사람이 쓴 TB의 시나리오나 검증 방식은 일부러 넣지 않는다
(LLM이 사람 TB를 베끼지 않고 명세에서 스스로 자극을 설계하는지 평가하기 위함).

| 항목 | 내용 |
|---|---|
| 구조 | top `sync_fifo` (포트: ck, reset, wr_en, rd_en, data_in[7:0], data_out[7:0], full, empty) |
| 깊이/폭 | 8개, 8비트 |
| 쓰기 | `wr_en`이 1이고 full이 아니면 `data_in`이 저장됨 |
| 읽기 | 동기 읽기: `rd_en`이 1이고 empty가 아니면 클럭 에지에서 `data_out`이 가장 오래된 데이터로 갱신되어 다음 사이클에 보임. 읽기가 없으면 `data_out`은 값을 유지하고, 리셋으로 지워지지 않음 |
| full에서 write | 무시 |
| empty에서 read | 무시 |
| 동시 write+read | empty면 write만, full이면 read만, 그 외는 둘 다 수행 |
| full / empty | 저장된 개수가 8이면 `full`, 0이면 `empty`. 개수는 클럭 에지에서 갱신되고 `full`/`empty`는 그 개수에서 바로 나옴 (에지 직후 값이 바뀜) |
| 리셋 | `reset` 비동기, active high. 리셋되면 저장된 개수가 0이 되어 `empty=1`, `full=0` |
