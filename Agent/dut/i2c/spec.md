# i2c_system 명세 (TB Generator 입력용)

이 파일은 **동작 명세만** 담는다. 사람이 쓴 TB의 시나리오나 검증 방식은 일부러 넣지 않는다
(LLM이 사람 TB를 베끼지 않고 명세에서 스스로 자극을 설계하는지 평가하기 위함).

| 항목 | 내용 |
|---|---|
| 구조 | top `i2c_system` = I2C Master 1개 + I2C Slave 1개가 `SCL`, `SDA`로 연결된 폐루프. Slave 주소는 `7'h42` 고정 |
| 포트 | 입력 `ck`, `reset`, `start`, `rw`, `addr[6:0]`, `master_tx_data[7:0]`, `slave_tx_data[7:0]` / 출력 `master_rx_data[7:0]`, `slave_rx_data[7:0]`, `SCL`, `SDA`, `busy`, `done`, `ack_error` |
| 클럭 | `ck`는 50MHz(주기 20ns). `SCL`은 100kHz(주기 500 ck = 10us). 내부적으로 SCL 1/4 주기(125 ck)마다 진행한다 |
| SDA | open-drain + pull-up: Master나 Slave 중 하나라도 당기면 0, 아무도 당기지 않으면 1 |
| 리셋 | `reset`은 비동기, active high. 리셋되면 `SCL=1`, `SDA=1`, `busy=0`, `done=0`, `ack_error=0`, `master_rx_data=0`, `slave_rx_data=0`이 되고 진행 중이던 트랜잭션은 중단된다. 리셋이 풀린 뒤에는 정상 동작한다 |
| 유휴 | `SCL=1`, `SDA=1` |
| 시작 | `start`를 1로 올리고 `busy`가 1이 될 때까지 유지한 뒤 내린다. `start`를 계속 1로 두면 트랜잭션이 연속으로 반복된다 |
| 트랜잭션 | START → 주소 7비트 + R/W(0: 쓰기, 1: 읽기) → Slave ACK → 데이터 1바이트 → ACK/NACK → STOP. 모든 바이트는 **MSB first** |
| 쓰기 (`rw=0`) | Master가 `master_tx_data`를 보내고 Slave가 ACK(0)한다. 끝나면 `slave_rx_data = master_tx_data` |
| 읽기 (`rw=1`) | Slave가 `slave_tx_data`를 보내고 Master가 NACK(1)으로 끝낸다 (1바이트 읽기). 끝나면 `master_rx_data = slave_tx_data` |
| 주소 불일치 | `addr`가 Slave 주소와 다르면 ACK 자리의 SDA가 1(NACK)이 된다. Master는 데이터 단계 없이 STOP하고 `ack_error=1`이 된다. `ack_error`는 다음 트랜잭션 시작에서 0으로 돌아간다 |
| START / STOP | START: SCL=1에서 SDA 하강, 그 뒤 250 ck에 SCL 하강. STOP: SCL 상승 뒤 125 ck에 SCL=1에서 SDA 상승. 그 밖의 SDA 변화는 SCL=0일 때만 일어난다 |
| SCL 파형 | 비트마다 SCL high 250 ck, low 250 ck. 단 START 뒤 첫 low 구간은 375 ck. 데이터 비트와 ACK 비트는 SCL 상승 에지에서 샘플한다. STOP 직전에 SCL이 한 번 더 올라가고(이때 SDA=0) 그 상태에서 STOP |
| busy / done | `busy`는 트랜잭션 동안 1, STOP 뒤 125 ck에 0이 되고 같은 에지에서 `done`이 1이 되어 500 ck 동안 유지된다 |
| rx_data | 해당 방향의 정상 트랜잭션이 끝날 때만 갱신되고 그 밖에는 유지된다 (리셋으로만 지워짐) |
| 지원하지 않는 것 | 여러 바이트 전송, repeated START, clock stretching, 10비트 주소, 여러 Slave |
