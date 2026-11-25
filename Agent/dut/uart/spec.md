# UART 명세 (TB Generator 입력용)

이 파일은 **동작 명세만** 담는다. 사람이 쓴 TB의 시나리오나 검증 방식은 일부러 넣지 않는다
(LLM이 사람 TB를 베끼지 않고 명세에서 스스로 자극을 설계하는지 평가하기 위함).

| 항목 | 내용 |
|---|---|
| 구조 | top `UART` = `Baud_Rate_Generator` + `UART_TX` + `UART_RX`. TX와 RX는 서로 독립이다 (`tx`와 `rx`는 외부에서 연결) |
| 포트 | 입력 `ck`, `reset`, `tx_start`, `tx_data[7:0]`, `rx` / 출력 `tx`, `tx_busy`, `rx_data[7:0]`, `data_valid` |
| 클럭 | `ck`는 50MHz(주기 20ns). 115200bps, 1비트 = `ck` 434주기 |
| 프레임 | 8N1: start 비트(0) 1개, 데이터 8비트 **LSB first**, stop 비트(1) 1개. 유휴 레벨은 1 |
| 리셋 | `reset`은 비동기, active high. 리셋되면 `tx=1`, `tx_busy=0`, `data_valid=0`, `rx_data=0`이 되고 진행 중이던 송수신은 중단된다. 리셋이 풀린 뒤에는 정상 동작한다 |
| baud tick (TX) | TX 출력(`tx`, `tx_busy`)은 baud tick 에지에서만 바뀐다. 리셋이 풀린 뒤 `ck` 상승 에지를 1부터 세면 tick 에지는 435, 869, 1303, ... 번째(434의 배수 + 1, 435 이상)이다 |
| 송신 시작 | `tx_start`를 1로 올리고 `tx_busy`가 1이 될 때까지 유지한 뒤 내린다. TX가 유휴일 때 `tx_start=1`을 본 첫 tick 에지에서 `tx_data`를 래치하고, **다음** tick 에지에서 start 비트를 시작한다. 래치 후 `tx_data`가 바뀌어도 그 프레임에는 영향이 없다 |
| tx_busy | start 비트가 시작되는 에지에서 1이 되고 stop 비트가 끝나는 에지(start 시작 후 10비트)에서 0이 된다 |
| 연속 송신 | `tx_start`를 계속 1로 두면 stop 비트 뒤 1비트 유휴(`tx=1`) 후 다음 프레임이 시작되고 그동안 `tx_busy`는 1을 유지한다. 전송 중(`tx_busy=1`)에 들어온 짧은 `tx_start`는 무시된다 |
| 수신 | RX는 baud tick을 쓰지 않고 자체 카운터로 동작한다. 유휴에서 `rx=0`을 처음 본 에지부터 반 비트를 기다린 뒤 비트마다 434 `ck` 간격으로 각 비트 중앙에서 샘플한다 (mid-bit sampling). 송신측 비트 주기가 ±2% 달라도 정상 수신한다 |
| data_valid | `rx=0`을 처음 본 에지로부터 4123 `ck` 뒤(stop 비트 중앙, 9.5비트)의 에지에서 stop 비트가 1이면 `rx_data`를 갱신하고 `data_valid`를 1 `ck` 동안 1로 낸다. 프레임당 한 번이다 |
| stop 비트 오류 | stop 비트 샘플 값이 0이면 `data_valid`를 내지 않고 `rx_data`를 유지한다 |
| rx_data | 다음 정상 프레임이나 리셋 전까지 값을 유지한다 |
