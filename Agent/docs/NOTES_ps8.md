# Phase 8: 새 DUT(SPI)로 확장해 Phase 7의 한계가 일반적인지 확인

Phase 7의 Debug Agent는 sync_fifo 하나(17개 변형)에서만 측정했고, 그 세트를 보고 도구와 형식을 고쳤다. 그래서 일반 성능을 낙관할 수 있다.
Phase 8의 첫 목적은 **Agent를 수정하지 않은 채** 다른 종류의 RTL(FSM, 시프트 레지스터, 클럭 분주, 두 모듈 간 프로토콜)에서 같은 한계(클럭 논리 오해, 단계 제한, 증거 도구 미사용)가 나오는지 보는 것이다.
이 문서는 8-1(SPI DUT 준비)을 다룬다. Regression/Report와 통합 실행(`run_agent.py`)은 그 뒤다.

## 1. 8-1 입력 코드 검토 (사용자가 만든 SPI RTL과 TB)

사용자 코드를 이 환경의 Icarus로 실제로 돌려 확인했다 (xsim이 아님).

| # | 문제 | 확인한 내용 | 처리 |
|---|---|---|---|
| 1 | **골든 RTL의 start 위상 버그** | `start`가 `spi_clk`가 High일 때 들어오면 첫 비트가 사라지고 마지막에 MSB가 반복된다 (`B1`을 보냈는데 `63`을 받음). 위상 8곳 중 `spi_clk`=1인 4곳이 틀렸다 | 아래 3절의 수정 적용 (사용자가 직접 고치기로 함) |
| 2 | 사람 TB가 self-checking이 아님 | 값을 비교하지 않고 `$finish`만 한다. `CHECK_FAIL` 등 로그 규약이 없다. 단일 전송이라 우연히 통과하고, `master_tx_data=8'b10100101`은 비트 순서를 뒤집어도 같은 회문이다 | `tb_spi_sc.v`를 새로 작성 (원본 TB는 보존) |
| 3 | `Slave` 모듈이 없음 | TB가 `Slave`를 쓰는데 올려 준 `SPI_Slave.v`는 `SPI_FSM`, `SPI_TX`, `SPI_RX`를 부르고 이 모듈들은 없다 (옛 구조). 두 번 올려도 같은 파일이었다 | `Slave.v`를 TB 포트에 맞춰 작성 (`Slave_TX` + `Slave_RX`). **사용자의 실제 Slave와 다르면 바꿔야 함** |
| 4 | 파일 이름 충돌 | `SPI_RX.v`, `SPI_TX.v`가 둘씩 (`Master_RX`/`Slave_RX`, `Master_TX`/`Slave_TX`). 하네스는 같은 basename을 거부한다 | 모듈 이름과 같은 고유 파일명으로 정리 |
| 5 | top이 둘 | `Master`, `Slave`가 모두 최상위 후보다 | `spi_system` 래퍼를 top으로 추가 |

### start 위상 버그의 원인

`CS`가 `start`로 즉시 내려가는 조합 논리인데 `Master_TX`는 `negedge spi_clk`마다 `bit_cnt`를 올린다. `start`가 `spi_clk` High에서 들어오면 첫 상승 에지 **전에** 하강 에지가 한 번 끼어 `bit_cnt`가 1이 된다. 사용자 TB는 리셋 직후 200ns(`spi_clk`=0)에 한 번만 start를 넣어 우연히 통과한다.

### 수정안 비교 (Icarus, 임시 Slave, 단일 데이터로 확인)

| 수정 | 위상 8곳 | done 중 start | start 유지(연속) | 전송 중 리셋 |
|---|---|---|---|---|
| 원본 | 4곳 실패 | - | - | - |
| `start_q <= start;` (negedge) | 모두 정상 | **실패** | 두 번째부터 실패 | 정상 |
| `start_q <= start && (state == IDLE);` (negedge) | 모두 정상 | 정상 | 정상 | 정상 |

첫 번째 수정은 위상 문제만 고치고, FSM이 DONE에서 IDLE로 돌아온 직후 `start_q`가 이미 1이면 `CS`가 상승 에지 뒤에 내려가 같은 문제가 재현된다. 두 번째 수정이 `dut/spi/rtl/Master_FSM.v`에 들어 있다. TB 시나리오(위상 전체, done 중 start, 연속, 전송 중 리셋)는 이 차이를 구분한다.

## 2. 만든 것 (`dut/spi/`, `bugs/spi/`)

| 파일 | 내용 |
|---|---|
| `dut/spi/rtl/` | `clock_divider.v`, `Master_FSM.v`(수정본), `Master.v`, `Master_RX.v`, `Master_TX.v`, `Slave.v`(새로 작성), `Slave_RX.v`, `Slave_TX.v`, `spi_system.v`(top) |
| `dut/spi/spec.md` | 동작 명세만 (TB 시나리오 제외). spi_clk 타이밍, mode 0, MSB first, busy/done, 연속 전송, 리셋 |
| `dut/spi/tb/tb_spi_sc.v` | self-checking TB (timescale 지시문 없음). 비트 모니터, 전송 단위 검사, 유휴 구간 검사, 리셋 직후 상태, spi_clk 주기와 리셋 뒤 첫 에지, 데이터 선로가 하강 에지에서만 바뀌는지 |
| `bugs/spi/bugs.json` | 변형 30개 + 동등 변형 2개. `dut_top: spi_system` 포함 |

### TB 자극

비대칭 데이터, start가 `spi_clk` 모든 위상에서 들어오는 경우(56회 High, 24회 Low), done 중 start, start 유지로 3회 연속, 전송 중 리셋 3회(초반·중반·후반), 데이터가 있는 상태의 리셋, 고정 seed 랜덤 40회. 골든에서 검사 4094개, 불일치 0.

### 변형 카탈로그 (타입은 기존 6종에서 가장 가까운 것으로 지정)

| 타입 | 개수 | 예 |
|---|---|---|
| pointer | 8 | `bit_cnt` 비교값, LSB first, 시프트 방향, 비트 건너뜀 |
| flag | 4 | busy/done, CS를 DONE에서도 low |
| reset | 5 | 리셋 값, 리셋 후 DONE에서 시작 |
| guard | 7 | CS 게이팅 제거, start 게이팅 제거, CS 배선 |
| corner | 6 | 분주 비교값, DONE 고착, 상승 에지 데이터 변경 |
| (동등) | 2 | 도달 불가 `default` 분기, 어디에도 연결되지 않는 `load` 출력 |

메모리에 해당하는 변형은 없다. 타입을 늘리면 `tests/test_bugs.py`의 sync_fifo 타입 집합 검사가 깨져서 기존 타입을 썼다.
처음에는 30개 중 27개만 TB가 잡았다. 놓친 3개(Master/Slave TX가 상승 에지에서 데이터를 바꿈, 리셋 시 분주 카운터 시작값)는 **명세에 있는 동작을 TB가 검사하지 않던 것**이라 TB에 검사를 추가해(`MOSI/MISO_change_at_rising`, `spi_clk_first_edge`) 모두 잡게 했다. 동등 변형은 둘 다 PASS한다. 이 검출률은 TB를 변형 결과를 보고 보강한 뒤의 값이라 낙관적이다.

## 3. 사용자가 할 일

1. **골든 RTL 수정 적용** (Master_FSM.v). 사용자 파일에 아래 차이를 반영한다.
```verilog
    reg [2:0] bit_cnt;

    // start를 spi_clk negedge에서 IDLE일 때만 받아 CS와 FSM이 같은 신호(start_q)를 쓴다.
    reg start_q;
    always @(negedge spi_clk or posedge reset) begin
        if (reset) start_q <= 1'b0;
        else       start_q <= start && (state == IDLE);
    end

    assign CS = (state == IDLE && !start_q) ? 1'b1 : ((state == DONE) ? 1'b1 : 1'b0);
    ...
                IDLE: begin
                    ...
                    if (start_q) begin      // start -> start_q
```
2. `Slave.v`가 사용자의 실제 구현과 같은지 확인한다 (다르면 `dut/spi/rtl/Slave.v`를 교체하고 변형 카탈로그의 `Slave_*` 항목을 점검한다).
3. 실제 xsim에서 확인한다 (이 환경에서는 Icarus로만 확인했다).
```powershell
pytest -q tests/test_spi_dut.py                        # Icarus가 PATH에 있으면 골든/변형 검증까지 실행
python -m scripts.run_eval --dut spi                   # 사람 TB 기준선: 골든 PASS, 변형 30개 검출 (결과는 runs/dut_spi_eval_<시각>/)
```
4. 기준선이 맞으면 **Agent를 수정하지 않고** v0e와 같은 설정으로 평가한다.
```powershell
python -m scripts.llm_ping
python -m scripts.run_debug_eval --dut spi --dry-run
python -m scripts.run_debug_eval --dut spi --only B01 B15 B19 --no-cache --label spi0a   # 처음엔 일부로 규약 확인
python -m scripts.run_debug_eval --dut spi --no-cache --label spi0                       # 전체 (호출 약 240회 예상)
python -m scripts.verify_fixes --dut spi --label spi0                                   # 수정안 사후 검증 (LLM 호출 없음)
```

## 4. 측정 계획 (미리 정해 두는 판정 기준)

세트를 본 뒤에 기준을 바꾸지 않으려고 먼저 적는다.

| 볼 것 | 의미 |
|---|---|
| 위치 정확도 (exact, ±2줄) | sync_fifo(88%)와 비교. 표본 30개, 1회 실행이라 큰 차이만 의미가 있다 |
| 도구 사용 분포, 로그/TB/파형 조회를 쓴 케이스 수 | sync_fifo는 0/17. SPI에서도 0에 가까우면 구조적인 편향 |
| 단계 제한으로 끝난 케이스 (`max_steps`) | `rerun_sim`이 단계를 쓰는 문제가 일반적인지 |
| 수정안 분류 (fixed_golden / fixed_pass / still_fail / no_fix) | 틀린 수정안이 보고서에 실리는 비율 |
| 클럭 논리 의미 오해 | `count <= count` 같은 반복 패턴이 SPI(FSM, 시프트, 에지)에서도 나오는지. 케이스 JSON을 직접 읽어야 알 수 있다 |

결과를 본 뒤에 대응(단계 제한, 환각, 증거 도구 유도)을 고르고, 고친 뒤의 검증은 이 세트와 sync_fifo 세트 모두에서 한다.

## 5. 알려진 한계

- 이 환경에서는 Icarus로만 검증했고 xsim은 사용자가 확인해야 한다 (race 의미, `timescale` 처리 차이 가능).
- `Slave.v`는 TB 포트에 맞춰 내가 작성했다. 사용자의 실제 Slave와 다르면 결과가 달라진다.
- 변형 30개는 내가 정했다. 사용자 sync_fifo 세트와 달리 사람이 쓰지 않은 변형이라, 어떤 버그가 쉬운지에 내 편향이 있을 수 있다.
- 타입 분류가 sync_fifo의 6종에 맞춰져 있어 SPI에는 어색한 항목이 있다 (pointer가 시프트 방향, 비트 순서까지 포함).
- UART, I2C는 아직 없다.