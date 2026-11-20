# tests/data

파서와 VCD Reader 테스트에 쓰는 **실제 도구 출력 샘플**입니다. 손으로 만든 내용이 아니라 Vivado 2024.2를 실제로 실행해서 저장한 것입니다 (`StepResult.stdout`, 즉 콘솔 출력 기준).

> `sim.log` 파일은 콘솔과 달리 시스템 정보 헤더(프로세스 ID, 호스트 이름, OS, CPU 등)가 붙어서 샘플로 쓰지 않습니다.

## 로그 샘플

| 파일 | 상황 | 생성 방법 |
|---|---|---|
| `xvlog_ok.log` | 정상 컴파일 (파일 6개, 모듈 6개) | async FIFO 6개 소스로 `xvlog -sv -f files.f`, exit=0 |
| `xvlog_syntax_error.log` | `fifo_mem.v`의 세미콜론 누락 (에러 3건, 4번째 파일에서 멈춤) | 에러 주입본 `fifo_mem_err1.v`로 실행, exit=1 |
| `xelab_ok.log` | 정상 엘라보레이션 (`Built simulation snapshot snap`) | `xelab -debug typical async_fifo_tb -s snap`, exit=0 |
| `xelab_missing_top.log` | `xvlog` 실패 뒤 `xelab`을 **수동으로** 강제 실행 (top을 못 찾음, 위치 없는 에러) | exit=1. 자동 실행에서는 중단 정책 때문에 이 상황이 생기지 않음 |
| `xsim_ok.log` | 원본 TB, 마커 없이 정상 종료 (`$finish ... 402 ns ... Line 131`) | `collect_xsim_samples ok` |
| `xsim_pass_marker.log` | `$display("[TB] PASS")` | `collect_xsim_samples pass_marker` |
| `xsim_fail_marker.log` | `$display("[TB] FAIL: dummy check")` | `collect_xsim_samples fail_marker` |
| `xsim_error.log` | `$error("dummy error")` (`Error:` + `Time:` 줄, 시뮬 계속, `xsim` rc=0) | `collect_xsim_samples error` |
| `xsim_fatal.log` | `$fatal(1, "dummy fatal")` (`Fatal:` + `Time:` 줄, `$finish` 줄에 File/Line 없음) | `collect_xsim_samples fatal` |
| `xsim_pass_with_error.log` | `$error` 뒤에 `[TB] PASS` (마커와 에러 공존) | `collect_xsim_samples pass_with_error` |
| `xsim_hang.log` | `$finish` 없음, 10초 타임아웃으로 강제 종료 (`## run all`에서 끊김) | `collect_xsim_samples hang` |

샘플 재생성:

```powershell
python -m scripts.collect_xsim_samples          # 전부 (1~2분)
python -m scripts.collect_xsim_samples ok       # 하나만
```

`xsim_*.log`는 기준 TB(`Manual_test/tb/tb_async_fifo.v`)의 끝부분(`#50; $finish;`)만 바꾼 복사본으로 만듭니다. 원본 TB는 수정하지 않습니다.

## VCD 샘플

| 파일 | 상황 |
|---|---|
| `ok_async_fifo.vcd` | 기준 TB 정상 실행 (Tcl `open_vcd`/`log_vcd`로 생성, 7,083 bytes, 마지막 타임스탬프 `#400000`). Phase 3 VcdReader 테스트 입력 |

이 VCD에는 같은 ID를 공유하는 신호(예: `dut.wr_ck`, `c1.wr_ck`, `m1.wr_ck`가 ID `*`)가 있고, FIFO 메모리 배열(`mem`)은 VCD가 unpacked array를 지원하지 않아 포함되어 있지 않습니다.

## 사용하는 테스트

| 테스트 | 쓰는 샘플 |
|---|---|
| `test_log_parser.py` | 위 로그 전부 |
| `test_analyzer.py` | 위 로그로 `RunResult`를 조립 |
| `test_vcd_reader.py` (Phase 3) | `ok_async_fifo.vcd` |
