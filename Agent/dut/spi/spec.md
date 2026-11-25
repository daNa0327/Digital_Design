# spi_system 명세 (TB Generator 입력용)

이 파일은 **동작 명세만** 담는다. 사람이 쓴 TB의 시나리오나 검증 방식은 일부러 넣지 않는다
(LLM이 사람 TB를 베끼지 않고 명세에서 스스로 자극을 설계하는지 평가하기 위함).

| 항목 | 내용 |
|---|---|
| 구조 | top `spi_system` = SPI Master 1개 + SPI Slave 1개가 `spi_clk`, `CS`, `MOSI`, `MISO`로 연결된 폐루프 |
| 포트 | 입력 `ck`, `reset`, `start`, `master_tx_data[7:0]`, `slave_tx_data[7:0]` / 출력 `master_rx_data[7:0]`, `slave_rx_data[7:0]`, `spi_clk`, `CS`, `MOSI`, `MISO`, `busy`, `done` |
| 클럭 | `ck`는 50MHz(주기 20ns). Master가 `ck`를 50분주해 `spi_clk`(1MHz, 주기 1000ns)를 만든다. Slave는 자체 클럭이 없고 `spi_clk`와 `CS`를 따른다 |
| spi_clk | 리셋 중 0. 리셋이 풀린 뒤 `ck`의 25번째 상승 에지에서 처음 반전(상승)하고 이후 25 `ck` 주기(500ns)마다 반전한다 (idle 레벨 low) |
| 리셋 | `reset`은 비동기, active high. 리셋되면 `CS=1`, `busy=0`, `done=0`, `master_rx_data=0`, `slave_rx_data=0`, `spi_clk=0`이 되고 진행 중이던 전송은 중단된다. 리셋이 풀린 뒤에는 새 전송을 정상 수행한다 |
| 전송 단위 | 한 번의 전송은 8비트이며 `spi_clk` 상승 에지 8번 동안 `CS=0`이다 |
| 비트 순서 | MSB first. Master는 `master_tx_data`를 `MOSI`로, Slave는 `slave_tx_data`를 `MISO`로 동시에 보낸다 |
| 샘플링 | SPI mode 0: 데이터 선로(`MOSI`, `MISO`)는 `spi_clk` 하강 에지에서 바뀌고 상승 에지에서 샘플된다. 첫 번째 비트는 `CS`가 내려간 뒤 첫 상승 에지에서 샘플되는 MSB다 |
| 전송 시작 | `start`를 1로 올리고 `busy`가 1이 될 때까지 유지한 뒤 내린다. 시작은 `start`를 올릴 때의 `spi_clk` 위상과 무관하게 같은 결과(8비트 정상 전송)여야 한다. `CS`는 `spi_clk` 하강 에지에서 내려간다 |
| CS | 전송 구간에만 0이고 그 밖에는 1이다. 전송이 끝나면(마지막 비트를 샘플한 에지 직후) 1이 된다 |
| busy | 첫 번째 비트를 샘플한 에지에서 1이 되고, 마지막(8번째) 비트를 샘플한 에지에서 0이 된다 |
| done | 마지막 비트를 샘플한 에지에서 1이 되어 `spi_clk` 2주기 동안 유지된다. 이후 0이다 |
| 수신 데이터 | `CS=0`인 동안 상승 에지마다 한 비트씩 시프트되어 `done`이 1이 되는 시점에 최종값이 된다. 전송 후 `master_rx_data`는 `slave_tx_data`, `slave_rx_data`는 `master_tx_data`와 같다. `CS=1`인 동안은 값을 유지한다 (리셋으로만 지워짐) |
| 연속 전송 | `done`이 1인 동안 또는 직후에 `start`를 올리면 다음 `spi_clk` 구간에서 새 전송이 시작된다. `start`를 계속 1로 유지하면 전송이 연속으로 반복되고 매번 8비트 정상 전송이다 |
