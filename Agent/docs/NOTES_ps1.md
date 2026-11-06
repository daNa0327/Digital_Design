# Phase 1 NOTES: XsimSim 어댑터

> RTL Verification AI Agent 개발의 Phase 1 기록.
> 목적: Phase 0에서 손으로 하던 `RTL + TB → 로그 + VCD`를 Python 함수 하나로 자동화한다.
> 이 단계에서는 **로그를 해석하지 않는다.** 단계별 원본 사실(종료 코드, 출력, 시간, VCD 경로)만 돌려준다. PASS/FAIL 판정은 Phase 2.
> 작성 기준일: 2026-11-03 / 대상 DUT: async FIFO (Phase 0과 동일)

상태 표기: ✅ 확인됨 · ⚠️ 부분 확인/추정 · ❓ 미확인(가설) · ⏸ 보류

---

## 1. 환경

| 항목 | 내용 |
|---|---|
| Python | 3.15.2 (신규 설치) |
| 가상환경 | `Agent/.venv` (터미널을 새로 열 때마다 `Activate.ps1` 필요) |
| 테스트 | pytest 9.2.0, pluggy 1.7.0 |
| 시뮬레이터 | Vivado 2024.2 xsim (Phase 0과 동일, PATH 등록 완료) |
| `shutil.which('xvlog')` | `C:\Xilinx\Vivado\2024.2\bin\xvlog.BAT` (`.BAT` 래퍼를 찾아 호출 가능) |
| Git | 저장소 루트는 상위 `Verilog/`, `Agent/`는 그 하위 폴더 |

환경 설정 중 겪은 일:

- PowerShell 실행 정책이 `Activate.ps1`을 막음 → `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
- Python이 PATH에 없어 `python`, `py` 모두 인식 안 됨 → 설치 시 "Add python.exe to PATH" 체크
- 스크립트는 반드시 **`Agent/` 루트에서 `python -m scripts.<이름>`** 으로 실행 (`python scripts/x.py`는 `sim` 패키지를 못 찾음)
- `pytest.ini`의 `pythonpath = .`은 pytest에만 적용됨

## 2. 프로젝트 구조

```
Agent/
├── core/
│   └── models.py              # StepResult, RunResult (원본 사실만 담는 데이터 틀)
├── sim/
│   ├── base.py                # Simulator 추상 클래스
│   ├── runner.py              # run_tool(): 도구 한 단계 실행 (타임아웃, 트리 종료)
│   ├── xsim.py                # XsimSim: xvlog → xelab → xsim 조율
│   ├── workdir.py             # new_workdir(): 실행마다 고유 폴더 경로 생성
│   └── templates/run.tcl.tmpl # VCD 덤프용 Tcl 템플릿
├── scripts/
│   ├── run_once.py            # CLI: 한 번 실행하고 결과 요약 출력
│   └── try_*.py               # 개발 중 임시 확인용 (run_once로 대체됨)
├── tests/
│   ├── data/                  # 파서 테스트용 실제 로그/VCD 샘플
│   ├── test_models.py
│   ├── test_runner.py
│   └── test_xsim_adapter.py
├── Manual_test/               # Phase 0 실습 (dut/, tb/, runs/manual, NOTES.md)
├── runs/                      # 실행별 workdir (git 무시)
├── pytest.ini
└── requirements.txt
```

`tests/data/` 샘플 (모두 실제 xsim 출력):

| 파일 | 상황 |
|---|---|
| `xvlog_ok.log`, `xelab_ok.log`, `sim_tcl_ok.log` | 정상 실행 |
| `xvlog_syntax_error.log` | `fifo_mem`의 세미콜론 누락 |
| `xelab_syntax_error.log` | 이름과 달리 **`xvlog`가 실패한 뒤 `xelab`을 돌린 로그** (top을 못 찾음). `xelab_missing_top.log`로 개명하거나 README에 설명 필요 |
| `ok_async_fifo.vcd` | Phase 3 VcdReader 테스트용 |

## 3. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 구조 | `Simulator` 추상 클래스 + `XsimSim` 구현 | xsim에 대한 지식(3단계, 명령, Tcl, 로그 위치)을 한 곳에 가둠. 이후 iverilog 등 추가 시 Agent 코드는 불변 |
| 책임 범위 | Phase 1은 **사실만 수집**, 판정은 Phase 2 | 파서를 고쳐도 실행부가 영향받지 않게 분리 |
| 출력 수집 | stdout + stderr를 하나로 합침 | 터미널에서 본 순서 그대로 보존. 콘솔 출력과 로그 파일 내용이 같음을 Phase 0에서 확인 |
| 종료 코드 | 0이 아니어도 예외를 내지 않고 **값으로 기록** (`check=False`) | 이 프로젝트에서 종료 코드 1은 수집 대상 데이터 |
| 도구 없음 | `FileNotFoundError` | DUT의 결과가 아니라 **환경 문제** |
| 소스 파일 없음 | `FileNotFoundError` | 호출 측 실수. `StepResult`에는 DUT 결과만 담음 |
| 타임아웃 | `returncode=None`, `timed_out=True` | 강제 종료한 프로세스를 정상 종료 코드와 구분 |
| workdir | 실행마다 새 폴더, **이미 있으면 `FileExistsError`** | 이전 `xsim.dir` 재사용으로 에러가 가려지는 문제 차단 (6.2 참고) |
| 중단 정책 | `xvlog`/`xelab`이 실패하거나 타임아웃이면 **다음 단계를 실행하지 않음** | 실패한 컴파일 위에서 `xelab`을 돌려도 파생 에러만 나옴 |
| 단계별 타임아웃 기본값 | `xvlog` 60초, `xelab` 120초, `xsim` 60초 | 실측 최대 8.3초(`xelab`). DUT가 커질 것을 감안해 넉넉히 |
| 경로 | `files.f`에 **절대경로(POSIX 형식)** 로 기록 | 실행 위치에 무관 (`C:/Users/...` 형식을 `xvlog`가 정상 처리함) |

## 4. 도구 동작 확인 (코딩 전 수동 실험)

종료 코드와 에러 형식을 추측하지 않고 `echo $LASTEXITCODE`로 직접 확인했다.

| 상황 | 종료 코드 | 비고 |
|---|---|---|
| 정상 `xvlog` | 0 | |
| 정상 `xelab` | 0 | `Built simulation snapshot snap` |
| 문법 에러 `xvlog` | **1** | `.bat` 래퍼가 종료 코드를 정상 전달함 (항상 0일 것이라는 우려는 해소) |
| `xvlog` 실패 후 `xelab` | **1** | 실행은 되지만 `XSIM 43-3225`로 실패 |

에러 로그 형식:

```
ERROR: [VRFC 10-4982] syntax error near 'end' [C:/.../fifo_mem_err1.v:21]
ERROR: [VRFC 10-8549] SystemVerilog keyword 'end' used in incorrect context [C:/.../fifo_mem_err1.v:21]
ERROR: [VRFC 10-8530] module 'fifo_mem' is ignored due to previous errors [C:/.../fifo_mem_err1.v:3]
```
```
ERROR: [XSIM 43-3225] Cannot find design unit work.async_fifo_tb in library work located at xsim.dir/work.
```

일반형: `ERROR: [<도구> <코드>] <메시지> [<파일>:<줄>]`

관찰 (Phase 2 파서 설계에 반영):

- ✅ **에러가 보고되는 줄이 원인 줄이 아닐 수 있다.** 지운 세미콜론은 앞줄에 있었는데 에러는 21번째 줄의 `end`로 보고됨. Debug Agent는 에러 줄 앞쪽도 봐야 한다.
- ✅ **첫 `ERROR`가 주 원인이고 나머지는 연쇄 에러**(`10-8549`, `10-8530`).
- ✅ **`xvlog`는 에러가 난 파일에서 멈추고 그 뒤 파일은 분석하지 않는다.** 에러 파일이 4번째였을 때 `Analyzing`이 4개만 출력됨. 에러 파일 뒤의 파일에 있는 문제는 첫 에러를 고친 뒤에야 보일 수 있다.
- ✅ **`xelab`의 에러는 상위 단계 실패의 결과일 수 있다.** "top을 못 찾는다"는 메시지의 진짜 원인은 `xvlog` 단계에 있다.
- ⚠️ **이전 `xsim.dir`이 에러를 가렸을 가능성.** `xsim.dir`이 남은 폴더에서 일부 파일이 분석되지 않았는데도 `xelab`이 성공했고, `xsim.dir`을 지우자 `xelab`이 실패했다. 이전 컴파일 결과가 재사용된 것으로 **추정**하며, 파일을 하나 빼서 확정하는 실험은 하지 않았다. 어느 쪽이든 실행마다 새 workdir를 쓰는 근거가 된다.

실행 시간 (환경과 캐시에 따라 편차가 큼):

| 단계 | 측정값 |
|---|---|
| `xvlog` | 2.5 ~ 5.2초 (첫 실행이 느림) |
| `xelab` | 3.0 ~ 8.3초 (첫 실행이 느림) |
| `xsim` (async FIFO, 402ns 시뮬) | 4.6초 |
| 전체 | 약 10.4초 |

## 5. 구현

### 5.1 `core/models.py`

```python
@dataclass
class StepResult:
    name: str                 # "xvlog" | "xelab" | "xsim"
    cmd: list[str]
    returncode: int | None    # 타임아웃으로 강제 종료했다면 None
    stdout: str               # stdout + stderr 합친 출력
    duration_s: float
    timed_out: bool = False

@dataclass
class RunResult:
    workdir: str
    steps: list[StepResult] = field(default_factory=list)
    stopped_at: str | None = None   # 중단 정책으로 멈춘 단계 이름
    vcd_path: str | None = None
    total_duration_s: float = 0.0
```

- `field(default_factory=list)`: 가변 기본값을 객체마다 새로 만들기 위함 (`= []`로 쓰면 dataclass가 `ValueError`로 막음)
- `returncode: int | None`: `0`이나 `-1`로 채우면 정상 종료와 구분되지 않음

### 5.2 `sim/runner.py`: `run_tool()`

```python
def run_tool(name, args, cwd, timeout=None) -> StepResult:
    exe = shutil.which(name)               # 없으면 FileNotFoundError
    proc = subprocess.Popen([exe, *args], cwd=cwd,
                            stdout=PIPE, stderr=STDOUT, text=True, errors="replace")
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)                   # taskkill /PID <pid> /T /F
        stdout, _ = proc.communicate()     # 죽인 뒤 남은 출력을 거둠
    ...
```

| 부분 | 이유 |
|---|---|
| `shutil.which` | `.BAT` 래퍼의 전체 경로를 얻어 호출 |
| `cwd=workdir` | `xvlog.log`, `xsim.dir`이 workdir 안에 생김 (격리의 핵심) |
| `errors="replace"` | 한글 Windows(cp949)에서 해석 불가 바이트가 있어도 죽지 않음 |
| `Popen` + `taskkill /T /F` | `.BAT` → `xsim.exe` 구조에서 래퍼만 죽이면 자식이 남을 수 있음 (5.5 참고) |
| 타임아웃 후 `communicate()` 재호출 | 죽기 전까지의 출력을 `stdout`에 보존 |

### 5.3 `sim/xsim.py`: `XsimSim.run(files, top, workdir)`

```
1. 소스 파일 검증 (없으면 FileNotFoundError)
2. workdir 생성 (이미 있으면 FileExistsError)
3. files.f (절대경로), run.tcl (템플릿 치환, UTF-8 BOM 없음) 생성
4. xvlog -sv -f files.f
   xelab -debug typical <top> -s snap
   xsim snap -tclbatch run.tcl -log sim.log
   각 단계 StepResult 기록. 실패/타임아웃이면 stopped_at 기록 후 중단
5. dump.vcd가 있으면 vcd_path 기록
```

`run.tcl.tmpl`:
```
open_vcd {vcd_name}
log_vcd [get_objects -r /*]
run {run_time}
close_vcd
quit
```

Tcl에 중괄호 `{ }`를 직접 쓰게 되면 `str.format` 규칙상 `{{ }}`로 두 번 써야 한다.

### 5.4 `scripts/run_once.py`

```powershell
python -m scripts.run_once --top async_fifo_tb --label fifo `
  --files Manual_test/dut/async_fifo.v Manual_test/dut/bin2gray.v Manual_test/dut/fifo_ctrl.v `
          Manual_test/dut/fifo_mem.v Manual_test/dut/synchronizer.v Manual_test/tb/tb_async_fifo.v
```

workdir는 `runs/<YYYYMMDD_HHMMSS>_<label>_<4자리 hex>`로 생성된다. 같은 초에 두 번 실행해도 충돌하지 않도록 랜덤 접미사를 붙였다.

### 5.5 타임아웃과 프로세스 트리 종료

```
Python ──▶ xsim.BAT (cmd.exe 래퍼) ──▶ xsim.exe (실제 시뮬레이터)
```

`$finish`가 없는 TB는 시뮬이 끝나지 않는다. 타임아웃이 없으면 Agent 전체가 멈춘다.

- ❓ **`subprocess.run(timeout=)`이 이 환경에서 실제로 멈추는지는 실험하지 않았다.** Windows에서 자식이 파이프를 쥐고 있으면 kill 뒤의 출력 수집에서 대기할 수 있다는 알려진 문제를 근거로 `Popen` + 트리 종료 방식을 택했다.

## 6. 검증 결과

### 6.1 정상 케이스 (Phase 0과 대조) ✅

| 항목 | 기대 (Phase 0) | 결과 |
|---|---|---|
| 세 단계 종료 코드 | 0 | `rc=0` 3개 (2.8초 / 3.0초 / 4.6초) |
| `stopped_at` | `None` | `None` |
| `$finish` | `402 ns ... Line 131` | 동일 |
| VCD 마지막 타임스탬프 | `#400000` | `#400000`, `0!`, `0*` |
| 생성 파일 | | `files.f`, `run.tcl`, `sim.log`, `snap.wdb`, `xvlog/xelab.log`, `dump.vcd`가 모두 workdir 안에 격리됨 |

### 6.2 에러 케이스 (중단 정책) ✅

`fifo_mem_err1.v`로 교체해서 실행:

```
xvlog  rc=1 timed_out=False 2.5s
stopped_at: xvlog
vcd_path  : None
```

`xelab`, `xsim`은 실행되지 않았다.

### 6.3 타임아웃 (실제 Vivado) ✅

`$finish`를 주석 처리한 TB 복사본(원본 TB는 수정하지 않음)으로 `xsim` 타임아웃 10초 설정:

| 항목 | 결과 |
|---|---|
| `xvlog` / `xelab` | `rc=0` (3.7초 / 8.3초) |
| `xsim` | `rc=None`, `timed_out=True`, **10.4초**에 반환 |
| 자식 프로세스 | `Get-Process xsim*` 출력 없음 (**남지 않음**) |
| 타임아웃 시점의 출력 | `run -all`까지의 로그가 `stdout`에 보존됨 |

### 6.4 자동 테스트: 15 passed ✅

| 파일 | 테스트 | 검증 내용 |
|---|---|---|
| `test_models.py` | 2 | 기본값, 인스턴스 간 `steps` 비공유 |
| `test_runner.py` | 6 | 도구 없음 → 예외 / 비정상 종료 코드를 예외 없이 기록 / stdout·stderr 병합 / `cwd` 적용 / **타임아웃 시 프로세스 트리 종료** / 빠른 프로세스는 타임아웃 미발동 |
| `test_xsim_adapter.py` | 7 | 단계 순서 / `xvlog` 실패 시 중단 / `xelab` 실패 시 중단 / 소스 없음 예외 / 기존 workdir 예외 / 생성 파일 내용 / **async FIFO end-to-end (Vivado 필요, 없으면 skip)** |

- Vivado 없이 도는 테스트는 `monkeypatch`로 `sim.xsim.run_tool`을 가짜로 바꿔 **조율 로직(순서, 중단 정책)만** 검증한다.
- 프로세스 트리 종료 테스트는 "부모 파이썬이 오래 도는 자식을 띄우는 구조"로 `.BAT` → `xsim.exe`를 흉내 내고, 타임아웃 후 자식 PID가 `tasklist`에 남지 않는지 확인한다 (Windows 전용).

## 7. 한계 및 미확인

| 항목 | 상태 | 비고 |
|---|---|---|
| `xsim`의 종료 코드 (`$error`, `$fatal`) | ❓ | 확인한 적 없음. 지금은 0이 아니면 `stopped_at="xsim"`으로만 기록하고 의미 해석은 Phase 2 |
| `$error`/`$fatal`/`[TB] PASS|FAIL`의 xsim 로그 형식 | ❓ | 샘플 수집 필요 (TB 복사본에 삽입 후 `run_once`) |
| 타임아웃으로 죽인 `xsim`의 VCD | ❓ | `close_vcd`가 실행되지 않아 비었거나 잘렸을 수 있음. `vcd_path`는 파일이 있으면 기록하지만 **완전하다는 보장은 없음**. Phase 3에서 고려 |
| 타임아웃의 비Windows 지원 | ⏸ | `_kill_tree`는 Windows 기준. 다른 OS는 `proc.kill()`만 호출 |
| 경로에 공백이 있는 경우 | ⏸ | `files.f`에 따옴표가 필요할 수 있음. 현재 경로에는 공백 없음 |
| `xelab` 첫 실행 시간 편차 | ⚠️ | 8.3초 → 3.0초. 도구 로딩/캐시 효과로 **추정** |
| 병렬 실행 | ⏸ | workdir는 고유하지만 동시 실행 시 부하는 확인하지 않음 |

Phase 0에서 이어진 항목:

- ⏸ **async FIFO `empty` 계산 비대칭**: 코드상 사실은 확인됨, 오동작은 시뮬 미확인. Agent 완성 후 수정하면서 적용 사례로 문서화 예정.
- ⏸ **골든 DUT 문제**: 위 DUT는 골든이 될 수 없으므로 Phase 4에서 평가용 골든은 별도 DUT(예: Sync FIFO)로 시작.
- ⏸ **기준 TB가 self-checking이 아님**: 버그 탐지율 기준선으로 쓸 수 없으며 별도 TB 필요.

## 8. 작업 중 얻은 교훈

- **테스트 개수를 기대값과 비교한다.** 테스트 파일을 덮어쓰면서 기존 테스트 하나가 사라진 적이 있다 (3 → 5 → 6 passed로 이어지며 발견). 실패가 아니라 검사가 조용히 줄어드는 형태라서 `passed` 숫자를 기대값과 대조해야 발견된다.
- **코드 파일에 설명 문구를 붙여 넣지 않는다.** 개념 설명표를 파일 맨 위에 붙여 넣었다가 문자열 안의 `\m`이 `SyntaxWarning`을 냈다 (Python 3.15는 이런 경고를 앞으로 에러로 바꿀 예정). `python -W error -c "import sim.runner"`로 확인한다.
- **원격에 새 커밋이 있으면 push가 거절된다** (`fetch first`). `git pull` 후 push로 해결. `--force`는 쓰지 않는다.
- **`.gitignore` 범위**: `**/runs/**/*.log`, `*.vcd`, `*.out`, `Agent/runs/`. `Manual_test/runs/manual`의 `files.f`, `run.tcl`은 계속 추적된다.

## 9. 다음 단계 (Phase 2: 로그 해석과 `SimResult`)

| # | 할 일 | 방식 |
|---|---|---|
| 2-1 | `SimResult`, `ErrorItem` 모델 | `core/models.py`에 추가 |
| 2-2 | `xvlog` 로그 파서 | `tests/data/xvlog_*.log`로 **테스트를 먼저** 작성 |
| 2-3 | `xelab` 로그 파서 | 상위 단계 실패의 파생 에러 구분 규칙 포함 |
| 2-4 | `xsim` 로그 파서 | `$finish` 시각 추출, 마커/에러 처리. **새 샘플 수집 선행** |
| 2-5 | `analyze(RunResult, 요청 파일) → SimResult` | 우선순위 규칙 통합 |
| 2-6 | `run_once`에 판정 출력 연결 | |

상태 집합: `PASS` / `FAIL` / `NO_VERDICT` / `COMPILE_ERROR` / `ELAB_ERROR` / `TIMEOUT`

- `NO_VERDICT`: 끝까지 돌았지만 PASS/FAIL 마커가 없음. **"명시적 PASS 마커가 있을 때만 PASS"** 규칙을 지키면서 self-checking이 아닌 기준 TB의 정상 실행을 FAIL로 오판하지 않기 위함. 지금의 async FIFO 실행이 이 상태가 되어야 한다.
- 종료 시각은 VCD가 아니라 로그의 `$finish called at time : <t> <unit>` 줄에서 가져온다 (VCD는 값이 바뀔 때만 타임스탬프를 기록하므로 마지막 타임스탬프가 종료 시각과 다를 수 있음).
- 요청한 파일과 `xvlog`가 분석을 시작한 파일을 비교해 **미분석 파일 목록**을 결과에 담는다.

## 10. 명령어 요약

```powershell
cd C:\Users\Junyoung\Desktop\Verilog\Agent
.\.venv\Scripts\Activate.ps1

pytest -v                                    # 15 passed (Vivado 통합 테스트 포함 약 15초)
python -m scripts.run_once --top async_fifo_tb --label fifo --files <소스들>
Get-Content runs\<workdir>\dump.vcd -Tail 5  # 마지막 타임스탬프 확인
Get-Process xsim* -ErrorAction SilentlyContinue   # 남은 시뮬레이터 프로세스 확인
python -W error -c "import sim.runner"       # 경고가 에러로 바뀌어도 안전한지
```
