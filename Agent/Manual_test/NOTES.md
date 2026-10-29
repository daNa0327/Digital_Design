# Phase 0 NOTES: Vivado xsim 수동 실행

> RTL Verification AI Agent 개발의 Phase 0(수동 실행) 기록.
> 목적: 자동화 전에 `RTL + TB → 로그 + VCD`를 손으로 한 번 성공시키고, 실제 도구 동작을 파악한다.
> 작성 기준일: 2026-10-29 / 대상 DUT: async FIFO

상태 표기: ✅ 확인됨 · ⚠️ 부분 확인/추정 · ❓ 미확인(가설) · ⏸ 보류

---

## 1. 환경

| 항목 | 내용 |
|---|---|
| 시뮬레이터 | Vivado Simulator (xsim) v2024.2 (64-bit) |
| OS / 셸 | Windows, PowerShell |
| 편집기 | VS Code |
| PATH | `C:\Xilinx\Vivado\2024.2\bin` 등록 완료 (`where xvlog`, `xvlog -version`으로 확인) |
| 파형 확인 | VS Code 파형 뷰어 (GTKWave로는 아직 미확인) |

`where xvlog`에 `xvlog`와 `xvlog.bat`이 둘 다 나오는 것은 정상.

## 2. 프로젝트 구조

```
Agent/Manual_test/
├── dut/
│   ├── async_fifo.v        # top
│   ├── bin2gray.v
│   ├── fifo_ctrl.v
│   ├── fifo_mem.v
│   └── synchronizer.v
├── tb/
│   └── tb_async_fifo.v     # 파일명과 달리 module 이름은 async_fifo_tb
└── runs/
    └── manual/             # 수동 실행 작업 폴더
```

**원칙**: 원본 `dut/`, `tb/`는 수정하지 않고, 실험은 `runs/` 아래 복사본에서 한다.

## 3. 대상 설계

### 3.1 DUT (async FIFO)

| 항목 | 내용 |
|---|---|
| 포트 | `wr_ck, rd_ck, reset, wr_en, rd_en, data_in[7:0], data_out[7:0], full, empty` |
| 깊이/폭 | 8 x 8bit (주소 3비트, 포인터 4비트, parameter 없음) |
| 리셋 | **비동기 High 리셋** (`posedge ck or posedge reset`) |
| CDC | gray 포인터를 2단 FF 동기화 (`synchronizer`) |
| 읽기 출력 | `rd_ck` 에지에서 갱신되는 레지스터 (동기 읽기) |
| 초기값 | `fifo_mem`에 리셋이 없어 `data_out`은 첫 읽기 전까지 X |

### 3.2 TB (`async_fifo_tb`)

- 클럭: `wr_ck` 주기 10ns, `rd_ck` 주기 14ns
- `` `timescale 1ns/1ps ``, `$finish` 존재 (마지막)
- **`$dumpfile`/`$dumpvars` 없음**, **`$display`/비교 로직 없음 (self-checking 아님)**

| 시간(ns) | 동작 |
|---|---|
| 10 ~ 20 | `reset` = 1 |
| 40 ~ 110 | `wr_en`=1, `data_in` 01 → 08 (10ns 간격) |
| 120 / 130 | `data_in` = 09 / 0A (Overflow 시도) |
| 140 | `wr_en`=0, `rd_en`=1 (읽기 8회 구간) |
| 252 | `rd_en`=0 |
| 272 ~ 322 | `rd_en`=1 (Underflow 시도) |
| 322 | `wr_en`=1, `data_in`=AA |
| 332 | `rd_en`=1, `data_in`=BB (`wr_en`=1은 352까지 유지) |
| 352 | `wr_en`=0 |
| 402 | `$finish` |

`wr_en`=1이 BB 구간에서 20ns 지속되어 `wr_ck` 상승 에지(335, 345ns)에서 **BB가 2회 쓰이는 구조**. 의도한 동작인지 확인 필요.

## 4. 실행 절차

모든 명령은 `runs/manual`에서 실행.

### 4.1 파일 리스트 `files.f`

```
../../dut/async_fifo.v
../../dut/bin2gray.v
../../dut/fifo_ctrl.v
../../dut/fifo_mem.v
../../dut/synchronizer.v
../../tb/tb_async_fifo.v
```

### 4.2 컴파일 / 엘라보레이션

```bat
xvlog -sv -f files.f
xelab -debug typical async_fifo_tb -s snap
```

- top은 **파일명이 아니라 module 이름** (`async_fifo_tb`).
- `xvlog`: 6개 파일 모두 `Analyzing`, 에러 없음.
- `xelab`: `bin2gray, synchronizer, fifo_ctrl, fifo_mem, async_fifo, async_fifo_tb` 컴파일 후 `Built simulation snapshot snap`. `Time Resolution for simulation is 1ps`.

### 4.3 시뮬레이션 (로그만)

```bat
xsim snap -runall -log sim.log
```

- 정상 종료: `$finish called at time : 402 ns : File ".../tb_async_fifo.v" Line 131`
- TB에 출력문이 없어 로그에는 이 종료 메시지와 xsim 배너만 남는다.
- VCD는 생성되지 않는다 (정상).

### 4.4 시뮬레이션 + VCD (Tcl)

`run.tcl`
```tcl
open_vcd dump.vcd
log_vcd [get_objects -r /*]
run all
close_vcd
quit
```
```bat
xsim snap -tclbatch run.tcl -log sim_tcl.log
```

- `-runall`과 `-tclbatch`는 같이 쓰지 않는다 (Tcl 안에서 `run all` 호출).
- Tcl은 UTF-8/ASCII로 저장 (PowerShell `>` 리다이렉션은 UTF-16이 될 수 있음).

## 5. 실행 결과

| 항목 | 결과 |
|---|---|
| Tcl 실행 | ✅ `open_vcd`, `log_vcd`, `run all`, `close_vcd`, `quit` 모두 에러 없이 실행 |
| `$finish` 이후 Tcl | ✅ **`$finish` 뒤에도 `close_vcd`, `quit`이 실행됨** (이 TB 기준) |
| `dump.vcd` | ✅ 7,083 bytes |
| VCD 끝 부분 | ✅ 마지막 타임스탬프 `#400000` (1ps 해상도로 400ns) |

VCD는 **값이 바뀔 때만** 타임스탬프가 기록되므로, 마지막 타임스탬프(400ns)가 종료 시각(402ns)과 다른 것은 정상이다. 시뮬 종료 시각은 VCD가 아니라 **로그의 `$finish called` 줄**에서 가져와야 한다.

### 생성 파일

| 파일 | 의미 | Agent에서의 처리 |
|---|---|---|
| `xvlog.log`, `xelab.log` | 각 도구가 cwd에 자동 생성 (콘솔 출력과 동일) | 파싱 대상 |
| `sim.log`, `sim_tcl.log` | `-log`로 지정한 xsim 로그 | 파싱 대상 |
| `dump.vcd` | Tcl로 생성한 파형 | VcdReader 입력 |
| `snap.wdb` | Tcl 실행 시 자동 생성되는 xsim 파형 DB | 무시 |
| `xsim.dir/` | 컴파일 결과, 스냅샷 | 실행마다 새 workdir로 격리 |
| `*.pb`, `xsim.jou`, `xsim_숫자...` | 내부 파일, 저널, 백업 | 무시 |

`.gitignore` 권장: `runs/**/xsim.dir/`, `runs/**/*.log`, `runs/**/*.pb`, `runs/**/*.jou`, `runs/**/*.wdb`, `runs/**/*.vcd` (+ `xsim_*` 백업 파일은 확장자 확인 후 추가)

## 6. 관찰 및 한계

### 6.1 `mem` 배열은 VCD에 기록되지 않음 ✅

```
INFO: HDL object /async_fifo_tb/dut/m1/mem is an unpacked array.
VCD does not support unpacked array type according to IEEE LRM 1800-2009, section 21.7.5.
```

FIFO 메모리 내용은 VCD로 볼 수 없다. Debug Agent는 포인터와 `data_out`으로 간접 추론해야 한다. 메모리 조회가 필요하면 `.wdb`를 읽거나 디버그용 신호를 노출하는 방법을 Phase 7에서 검토.

### 6.2 VCD의 신호 alias ⚠️

`dump.vcd`에서 `wr_ck`를 검색한 결과:

```
14: $var reg  1 ! wr_ck     # TB의 wr_ck
24: $var wire 1 * wr_ck     # 이하 세 줄이 같은 ID '*'를 공유
38: $var wire 1 * wr_ck
83: $var wire 1 * wr_ck
```

- **① 같은 ID를 공유하는 alias**: `dut.wr_ck`, `c1.wr_ck`, `m1.wr_ck` (ID `*`). 값 이력은 하나뿐.
- **② ID는 다르지만 같은 net**: `tb.wr_ck`(`!`)와 `dut.wr_ck`(`*`).
- 파형 뷰어에서 `dut.wr_ck`, `c1.wr_ck`, `dut.reset` 등이 X로 보였던 것은, 뷰어가 ID를 공유하는 신호 중 하나만 표시하는 문제로 **추정**한다. 리셋이 정상 전달됐다는 근거는 `sync_wr2rd.reset` 펄스와 포인터 초기화.
- 확정하려면: GTKWave로 열어 해당 신호가 토글하는지 확인하거나, ID `*`의 값 변화 줄 수를 센다. (미수행)

### 6.3 기준 TB는 self-checking이 아님 ✅

`tb_async_fifo.v`는 출력/비교 로직이 없어 로그에 PASS/FAIL이 남지 않는다. 사람이 파형으로 판단하는 방식이므로 **버그 탐지율 기준선으로 쓸 수 없다.** 기준선용 self-checking TB(scoreboard 포함)는 별도로 작성해야 한다 (Phase 4 이전).

### 6.4 VCD 생성 방식 결론 ✅

- Vivado 환경에서 평소 쓰던 TB에는 `$dumpfile`이 없으므로, **Tcl(`open_vcd`/`log_vcd`) 방식을 주 방식**으로 채택. TB 수정이 필요 없다.
- `$finish`와 `close_vcd` 충돌 우려는 이 TB에서는 발생하지 않았다. 다른 DUT에서는 그때 다시 확인.

## 7. 파형 확인 결과

시간은 화면 픽셀로 환산한 **추정값(±3ns)**. 정밀 확인이 필요하면 구간 확대.

| # | 확인 | 결과 | 근거 |
|---|---|---|---|
| 1 | 리셋 후 X 잔존 | ✅ | `dut.wr_ptr`, `rd_ptr`이 리셋 직후 `0x0`. `rd_ck` 에지(7, 21ns)가 리셋 구간(10~20ns)에 없는데도 초기화 → 비동기 리셋 동작 |
| 2 | 8번째 쓰기 후 `full` | ✅ | `full`이 약 115ns에 상승 |
| 3 | Overflow 무시 | ✅ | `wr_ptr`이 `0x8`에서 정지 (09, 0A 구간에도 불변) |
| 4 | 읽기 순서/지연 | ⚠️ | `data_out`이 약 147ns(첫 `rd_ck` 에지)에 X에서 유효값으로 변하고 8번 변화 후 `0x8` 유지. 값별 순서(01→08)는 확대 확인 필요 |
| 5 | Underflow 무시 | ✅ | `empty`=1 구간(약 261~361ns)에서 `rd_ptr`이 `0x8` 유지 |
| 6 | AA/BB 쓰기 | ✅ | `wr_ptr`이 `0x8` → `0xb` (+3). AA, BB, BB 3회 쓰기, 최종 `data_out`=`0xbb` |
| 7 | CDC 지연 | ✅ | 첫 쓰기 후 `empty` 해제까지 약 32ns, 첫 읽기 후 `full` 해제까지 약 30ns |

gray 변환도 정합: `wr_ptr=0xb` ↔ gray `0xe`, 동기화 체인에도 `0xe` 전달.

## 8. RTL 분석: async FIFO의 `empty` 계산 비대칭

### 8.1 코드로 확인된 사실 ✅

`fifo_ctrl.v`에서 `full`과 `empty`의 계산 방식이 다르다.

```verilog
// 쓰기 쪽: next 포인터의 gray와 비교 (포인터 갱신과 같은 에지에서 반영)
full  <= (wr_gray_next == {~rd_gray_sync[3:2], rd_gray_sync[1:0]});

// 읽기 쪽: 갱신 전 현재 rd_gray와 비교 (포인터 증가보다 한 에지 늦게 반영)
empty <= (wr_gray_sync == rd_gray);
```

`rd_ptr_next`, `rd_gray_next`에 해당하는 신호가 없다.

### 8.2 오동작 가설 ❓ (시뮬 미확인)

마지막 항목을 읽은 에지에서 `empty`가 아직 0이므로, `rd_en`을 계속 High로 둔 채 FIFO를 비우면 한 번 더 읽혀 `rd_ptr`이 `wr_ptr`을 넘을 수 있다 (이후 `empty`가 다시 0이 되어 쓰레기 데이터를 읽는 상태).

- 현재 TB는 이 상황을 드러내지 못한다: 첫 읽기 구간은 252ns에 `rd_en`을 내렸고, 마지막 구간은 수동 추적상 약 413ns에 발생할 수 있는데 TB가 402ns에 끝난다.
- 기존 파형(첫 읽기 구간의 `empty` 상승이 마지막 읽기 다음 `rd_ck` 에지, 최종 `rd_ptr`=`wr_ptr`=`0xb`, `empty`=0)과는 모순되지 않는다.
- 확인 방법: TB 복사본의 마지막을 `#50; $finish;` → `#100; $finish;`로 늘려 다시 실행하고, 400~450ns에서 `rd_ptr`이 `0xb`→`0xc`로 넘어가고 `empty`가 1이 되었다가 다시 0이 되는지 본다.
- **현재 결정**: 수정하지 않고 보류. Agent 완성 후 수정하면서 실제 적용 사례로 문서화한다. 이때 README에는 "수동 분석으로 의심 → Agent가 자동으로 재현/원인 분석" 순서를 그대로 기록한다.

### 8.3 참고

- 비동기 리셋의 해제(deassertion)가 각 클럭 도메인에 동기화되어 있지 않다. 시뮬에서는 문제가 없지만 실제 하드웨어에서는 recovery/removal 이슈가 될 수 있는 구조.
- 이 DUT에 잠재 버그가 있다면 "골든은 반드시 PASS" 전제가 성립하지 않는다. Phase 4에서 평가용 골든은 별도 DUT(예: Sync FIFO) 또는 수정본으로 정한다.

## 9. Agent 설계에 반영할 결정

| 항목 | 결정 |
|---|---|
| 시뮬레이터 | xsim 주 백엔드, `Simulator` 추상 클래스 + `XsimSim` 어댑터 |
| 로그 | xvlog / xelab / xsim **로그가 3개로 나뉨** → 단계 이름과 함께 합쳐 판정 |
| 정상 종료 마커 | `$finish called at time : <t> <unit> : File "<path>" Line <n>` |
| PASS 판정 | 명시적 PASS 마커가 있을 때만 PASS. 마커가 없으면 PASS로 처리하지 않음 |
| 종료 시각 | VCD 마지막 타임스탬프가 아니라 **로그의 `$finish` 줄**에서 가져옴 |
| 신호 조회 | VcdReader는 **ID 기준으로 이력을 저장**하고 이름→ID를 별도 매핑 (같은 ID를 여러 이름이 공유) |
| alias | 도구가 신호를 반환할 때 alias 후보를 같이 반환. X를 근거로 결론 내기 전에 alias와 교차 확인 |
| 메모리 | VCD에 `mem` 없음 → 포인터/`data_out`으로 추론하거나 별도 방법 필요 |
| 실행 격리 | 실행마다 새 workdir, 원본 파일은 읽기 전용 |

VcdReader 저장 구조 (ID 덮어쓰기 방지):

```python
self.id2names = defaultdict(list)   # ID -> [계층 이름들]
self.name2id  = {}                  # 이름 -> ID
self.changes  = defaultdict(list)   # ID -> [(t, val)]
```

## 10. 보류 / 미수행

| 항목 | 상태 | 비고 |
|---|---|---|
| 로그 5종 수집 (컴파일 에러, 엘라보레이션 에러, `$error` FAIL, 타임아웃) | ⏸ | Phase 2에서 해당 판정 규칙을 만들 때 하나씩 생성 |
| `empty` 버그 확장 실험 (`#100; $finish;`) | ⏸ | 수정은 Agent 완성 후 |
| GTKWave로 alias/X 표시 재확인 | 미수행 | 6.2 참고 |
| 파형 #4 (읽기 값 순서 01→08) 확대 확인 | 미수행 | 235~260ns 등 읽기 구간 |

## 11. Phase 1 시작 전 확인할 것

복사본 폴더에서 5분이면 확인 가능.

| 질문 | 방법 | 설계에 쓰이는 곳 |
|---|---|---|
| 컴파일 에러 시 `xvlog`의 종료 코드는 0이 아닌가? | 세미콜론 삭제 후 `xvlog ...; echo $LASTEXITCODE` | 종료 코드로 실패를 판정할 수 있는지, 로그 파싱이 필수인지 |
| `xvlog`가 실패해도 `xelab`이 실행되는가? | 이어서 `xelab ...` 실행 | 단계마다 중단할지 여부 |

## 12. 다음 단계

1. 이 노트와 `.gitignore`, `files.f`, `run.tcl` 커밋
2. Phase 1: `XsimSim` 어댑터 (xvlog → xelab → xsim, workdir 격리, Tcl 템플릿 생성)
3. Phase 2: 로그 파서 + 공통 `SimResult` (필요한 에러 케이스를 이때 하나씩 생성)
4. Phase 3: VcdReader (ID 기준 저장, alias 처리, 구간 조회)

## 13. 명령어 요약

```bat
cd Manual_test\runs\manual
xvlog -sv -f files.f
xelab -debug typical async_fifo_tb -s snap
xsim snap -runall -log sim.log                          :: 로그만
xsim snap -tclbatch run.tcl -log sim_tcl.log            :: 로그 + dump.vcd
```

```powershell
Get-Item dump.vcd | Select-Object Length                # VCD 크기
Get-Content dump.vcd -Tail 5                            # 마지막 기록 확인
Select-String -Path dump.vcd -Pattern ' wr_ck '         # alias 확인
```
