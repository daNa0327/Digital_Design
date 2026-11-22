# Phase 2 NOTES: 로그 파서와 SimResult 판정

> RTL Verification AI Agent 개발의 Phase 2 기록.
> 목적: Phase 1이 만든 원본 사실(`RunResult`: 종료 코드, 출력, 시간)을 **해석된 결과(`SimResult`)** 로 바꾼다.
> LLM은 쓰지 않는다. 정규식과 우선순위 규칙만으로 구성한 결정적 계층이다.
> 작성 기준일: 2026-11-20 / 대상 DUT: async FIFO

상태 표기: ✅ 확인됨 · ⚠️ 부분 확인/추정 · ❓ 미확인(가설) · ⏸ 보류

---

## 1. 구조

```
XsimSim.run() ──▶ RunResult ──▶ analyze() ──▶ SimResult
                (원본 사실)     ├ parse_xvlog / parse_xelab / parse_xsim
                               └ 우선순위 규칙
```

| 파일 | 역할 |
|---|---|
| `core/models.py` | `ErrorItem`, `SimResult` 추가. `RunResult.sources`(요청한 소스), `SimResult.failed_stage` 추가 |
| `core/log_parser.py` | 단계별 파서 3개와 `time_to_ps()` (순수 함수, Vivado 불필요) |
| `core/analyzer.py` | `analyze(RunResult) -> SimResult` 판정 |
| `scripts/run_once.py` | 실행 후 판정(`status`, 에러 목록, 미분석 파일)까지 출력 |
| `scripts/collect_xsim_samples.py` | TB 끝부분만 바꾼 변형 6종을 실제로 돌려 xsim 로그 샘플 수집 |
| `tests/test_log_parser.py`, `test_analyzer.py`, `test_pipeline.py` | 파서, 판정, 실제 실행 end-to-end 검증 |

## 2. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 사실과 해석의 분리 | `RunResult`(Phase 1)와 `SimResult`(Phase 2)를 따로 둠 | 파서 규칙을 바꿔도 실행부가 영향받지 않고, 같은 `RunResult`를 다시 해석할 수 있음 |
| `RunResult.sources` | 어댑터가 실행에 쓴 소스를 스스로 기록 | `analyze(run)` 하나로 미분석 파일을 계산. 호출자가 목록을 따로 넘기지 않아도 됨 |
| `tb_verdict` vs `status` | TB가 한 말과 종합 판정을 분리 | TB는 PASS라고 했지만 시뮬레이터가 에러를 낸 경우를 구분 (`mix` 케이스) |
| `NO_VERDICT` 상태 | 끝까지 돌았지만 PASS/FAIL 마커가 없을 때 | "명시적 PASS 마커가 있을 때만 PASS" 규칙을 지키면서 self-checking이 아닌 기준 TB를 FAIL로 오판하지 않음 |
| 시각 단위 | `finish_time_ps`를 정수 ps로 통일 | 로그가 ns, us 등으로 나올 수 있음 |
| 종료 시각의 출처 | VCD가 아니라 로그의 `$finish called at time` | VCD는 값이 바뀔 때만 타임스탬프를 기록 |
| 에러 위치 필드 | `file`, `line`, `code`는 선택값 | 위치 없는 에러가 실제로 있음 (`XSIM 43-3225`, `$fatal`의 `$finish` 줄) |
| 주 원인 | 같은 단계의 **첫 에러만** `is_primary` | 나머지는 연쇄 에러 |
| 합성 에러 3종 | `EXIT_CODE`, `NO_SNAPSHOT`, `TB_FAIL` | 실패인데 설명할 `ERROR` 줄이 없을 때 Agent가 `errors`만 보고 이유를 알 수 있게 |
| 미분석 파일 | 요청 파일 − `xvlog`가 분석을 시작한 파일 | 에러 뒤의 파일은 문제없다고 오해하지 않게 (경로는 정규화 후 비교) |

## 3. 측정 결과 (코딩 전, 실제 xsim 실행)

`$error`, `$fatal`, 마커의 로그 형식은 추측하지 않고 TB 끝부분만 바꾼 변형 6종으로 측정했다.

| 질문 | 결과 |
|---|---|
| `xsim` 종료 코드 | ✅ 정상, `$error`, `$fatal` **모두 0**. 타임아웃만 `None` |
| `$error` 형식 | ✅ `Error: <메시지>` 다음 줄에 `Time: <t> <단위>  Iteration: N  Process: ...  Scope: ...  File: <경로> Line: N` |
| `$fatal` 형식 | ✅ `Fatal: <메시지>` + 같은 형식의 `Time:` 줄 |
| `$error` 후 계속 실행되는가 | ✅ 계속됨. `$finish called ... File "..." Line 131`까지 도달 |
| `$fatal` 후 | ⚠️ 즉시 종료로 **추정**. `$finish called at time : 402 ns` 줄이 `File`/`Line` 없이 나옴 |
| `$display("[TB] PASS")` | ✅ 줄 맨 앞에 그대로 출력 |
| 타임아웃 로그 | ✅ `## run all`에서 끊김. `$finish`, `## close_vcd`가 없음 |
| `sim.log`와 콘솔 출력 | ✅ **다르다.** 본문은 같고 파일 쪽에만 시스템 정보 헤더(프로세스 ID, 호스트 이름, OS, CPU, 메모리)가 붙음 |

설계에 미친 영향:

- **시뮬레이션 FAIL은 로그로만 판정한다.** 종료 코드가 에러가 있어도 0이다.
- **`$finish` 줄이 있다고 정상 종료가 아니다.** `$fatal` 로그에도 나온다.
- 에러 위치는 둘째 줄(`Time:`)에 있어서 두 줄을 한 묶음으로 읽는다. `Time:` 줄을 필수로 요구해서 TB가 `$display("Error: ...")`로 찍은 일반 출력과 구분한다 (대신 그런 문구는 에러로 잡히지 않으므로 TB 판정은 `[TB] FAIL` 규약으로만 인정).
- **파서는 `StepResult.stdout`(콘솔) 기준**이다. 샘플도 콘솔 기반만 쓴다. Phase 1 노트의 "콘솔과 로그 파일이 같다"는 `xsim` 로그에는 틀렸다.

## 4. 파서

### 4.1 `xvlog`

| 뽑는 것 | 로그 형식 |
|---|---|
| 분석을 시작한 파일 | `INFO: [VRFC 10-2263] Analyzing SystemVerilog file "<경로>" into library work` |
| 모듈 | `INFO: [VRFC 10-311] analyzing module <이름>` |
| 에러 | `ERROR: [<도구> <코드>] <메시지> [<파일>:<줄>]` (위치는 선택) |

- 필드 이름은 `attempted_files`(분석을 **시작한** 파일). 에러가 난 파일도 `Analyzing` 줄은 찍히기 때문.
- ✅ `xvlog`는 에러가 난 파일에서 멈추고 뒤 파일은 분석하지 않는다.
- ✅ 에러가 보고되는 줄이 원인 줄이 아닐 수 있다 (세미콜론 누락 → 다음 줄의 `end`).

### 4.2 `xelab`

| 뽑는 것 | 로그 형식 |
|---|---|
| 모듈 | `Compiling module work.<이름>` (의존성 순서, 말단 모듈부터) |
| 스냅샷 | `Built simulation snapshot <이름>` |
| 시간 해상도 | `Time Resolution for simulation is 1ps` |
| 에러 | `xvlog`와 같은 형식 (공통 함수로 처리) |

- 종료 코드 0이어도 스냅샷이 없으면 실패로 본다 (이중 확인).
- `Compiling package`, `interface` 등 SystemVerilog 항목은 일부러 무시했다. SV 확장 시 추가.
- ❓ parameter가 있는 모듈은 이름 뒤에 표기가 붙을 수 있다. 이 DUT에는 parameter가 없어 확인하지 못함.

### 4.3 `xsim`

| 뽑는 것 | 비고 |
|---|---|
| `$finish called at time : <t> <단위>` | `File ... Line ...` 부분은 선택 (`$fatal`에는 없음) |
| `[TB] PASS` / `[TB] FAIL: <문구>` | 줄 맨 앞에서만 인정. 여러 개일 수 있어 목록으로 보관 |
| `Error:`/`Fatal:` + `Time:` 줄 | `severity`, `time_ps`, 파일·줄 포함 |

## 5. 판정 규칙 (`analyze`)

위에서 아래로 처음 해당하는 것으로 결정한다.

| 순서 | 조건 | 상태 |
|---|---|---|
| 1 | 어느 단계든 타임아웃 | `TIMEOUT` |
| 2 | `xvlog` 종료 코드 ≠ 0 또는 `ERROR` 있음 | `COMPILE_ERROR` |
| 3 | `xelab` 종료 코드 ≠ 0, `ERROR` 있음, 스냅샷 없음 | `ELAB_ERROR` |
| 4 | `xsim` 종료 코드 ≠ 0, `Error:`/`Fatal:`, `[TB] FAIL` | `FAIL` |
| 5 | `[TB] PASS`가 있고 위에 해당 없음 | `PASS` |
| 6 | 그 외 (마커 없이 끝까지 실행) | `NO_VERDICT` |

- **4번이 5번보다 먼저**다. `pass_with_error` 샘플이 검증한다.
- `xsim` 종료 코드 ≠ 0은 아직 관측한 적이 없는 **예방적 규칙**이다 (❓).
- 앞 단계가 모두 성공인데 `xsim` 기록이 없으면 조용히 `NO_VERDICT`로 넘기지 않고 `ValueError`.
- `failed_stage`는 판정을 결정한 단계. 타임아웃이 어느 단계에서 났는지도 알려 준다.

## 6. 검증 결과

### 6.1 실제 Vivado 실행 8종 ✅

`run_once`로 실제 실행한 결과가 모두 기대와 일치했다.

| 실행 | `status` | `tb_verdict` | 핵심 확인 |
|---|---|---|---|
| `ok` (원본 TB) | `NO_VERDICT` | `None` | `finish: 402000 ps`, 마커 없는 정상 종료를 PASS로 오판하지 않음 |
| `pass` | `PASS` | `PASS` | |
| `fail` | `FAIL (xsim)` | `FAIL` | `TB_FAIL: dummy check` |
| `err` | `FAIL (xsim)` | `None` | `xsim` rc=0인데 로그로 FAIL, `@402000ps`, 파일:줄 포함 |
| `fatal` | `FAIL (xsim)` | `None` | 심각도 `FATAL` |
| `mix` | `FAIL (xsim)` | **`PASS`** | TB가 한 말과 종합 판정이 다름 |
| `hang` | `TIMEOUT (xsim)` | `None` | 10.2초에 종료 |
| `cerr` | `COMPILE_ERROR (xvlog)` | | 에러 3건(첫 건만 `*`), 미분석 파일 `synchronizer.v`, `tb_async_fifo.v` |

### 6.2 자동 테스트: 47 passed ✅

| 파일 | 개수 | 내용 |
|---|---|---|
| `test_models.py` | 6 | 데이터 모델 기본값 |
| `test_runner.py` | 6 | `run_tool` (종료 코드, 병합, cwd, 타임아웃과 프로세스 트리 종료) |
| `test_xsim_adapter.py` | 7 | 단계 순서, 중단 정책, 입력 검증, 생성 파일, 실제 Vivado 통합 1 |
| `test_log_parser.py` | 13 | `xvlog` 3, `xelab` 2, `xsim` 8 (`time_to_ps` 포함) |
| `test_analyzer.py` | 13 | 판정 규칙 전부 |
| `test_pipeline.py` | 2 | 실제 Vivado 실행 → `analyze` (마커 없음, 컴파일 에러 + 미분석 파일) |

## 7. 한계 및 미확인

| 항목 | 상태 | 비고 |
|---|---|---|
| `xsim` 종료 코드 ≠ 0 | ❓ | 관측한 적 없음 |
| `$fatal`이 시뮬을 직접 끝낸다는 것 | ⚠️ | `$finish` 줄 형식으로 추정 |
| 타임아웃으로 죽인 `xsim`의 VCD | ⚠️ | Phase 3에서 확인: 읽을 수 있는 불완전한 파일이 남고 끊기는 지점은 비결정적 (마지막 줄은 온전). 잘린 줄을 견디도록 설계함 (`docs/NOTES_ps3.md` 3.2절) |
| TB의 `$display("Error: ...")` | ⏸ | 시뮬레이터 에러와 구분하려고 `Time:` 줄을 필수로 해서 에러로 잡히지 않음. `[TB] FAIL` 규약으로만 인정 |
| parameter 있는 모듈, SV 구문 | ⏸ | `xelab` 파서 확장 필요 |
| 샘플 로그의 로컬 경로 | ⚠️ | `C:/Users/Junyoung/...`가 들어 있음. 공개 시 치환 고려 (파서는 경로를 구조로만 다뤄 영향 없음) |

Phase 0, 1에서 이어진 항목 중 골든 DUT 문제와 self-checking TB는 Phase 4에서 sync FIFO로 해결했다 (`docs/NOTES_ps4.md`). async FIFO `empty` 비대칭은 계속 보류다.

## 8. 작업 중 얻은 교훈

- **샘플 로그는 직접 쓰지 않는다.** 파일이 없어 테스트가 실패했을 때 손으로 만든 `xsim_ok.log`가 실제 출력과 달랐다(버전 문구, `$finish` 줄 형식). 테스트는 통과해도 실제 로그 파싱을 증명하지 못한다. 샘플 생성 스크립트를 실행한다.
- **형식을 추측하지 않고 측정한다.** `$error`/`$fatal`을 직접 일으켜 보고서야 종료 코드가 0이라는 사실을 알았다. 이 사실이 판정 규칙의 핵심이 됐다.
- **검증 명령의 오류도 의심한다.** `Select-String`이 대소문자를 구분하지 않아 `Analyzing`이 12로 나왔다 (파일 줄 6 + `analyzing module` 6). `-CaseSensitive`로 확인.
- **테스트 개수를 기대값과 대조한다.** 파일 덮어쓰기로 테스트가 사라지거나, 구현 대신 테스트 코드가 `core/analyzer.py`에 저장되어 순환 import가 난 일이 있었다.
- **저장소 구조 확인.** `Agent/` 안에 별도 `.git`이 있어 VS Code가 다른 저장소 상태를 보여 줬다. `Test-Path Agent\.git`으로 확인.

## 9. 다음 단계 (Phase 3: VcdReader) — ✅ 완료, 결과는 `docs/NOTES_ps3.md`

| 확인된 사실 | 설계 |
|---|---|
| 같은 ID를 여러 신호 이름이 공유 | 이력을 **ID 기준**으로 저장, 이름→ID를 따로 |
| 뷰어가 alias를 X로 보여 줌 | 반환할 때 alias 목록 동반 |
| VCD는 값이 바뀔 때만 기록 | `value_at(t)`는 "t 이전의 마지막 변화값" |
| `mem` 배열은 VCD에 없음 | 조회 불가 신호임을 알림 |
| 타임아웃으로 죽인 파일은 잘렸을 수 있음 | 끊긴 마지막 값은 무시 |

| # | 내용 |
|---|---|
| 3-1 | 파서와 기본 조회 (`names`, `info`, `value_at`, `window`, `aliases`) |
| 3-2 | 클럭 에지 샘플링 (`sample_on_edge`) |
| 3-3 | 동일 net 후보 묶기, 조회 불가 신호 표시 |
| 3-4 | Agent에 노출할 도구 함수 (구간·개수 제한) |

## 10. 명령어 요약

```powershell
cd C:\Users\Junyoung\Desktop\Verilog\Agent
.\.venv\Scripts\Activate.ps1

pytest -q                                       # 47 passed (Vivado 통합 포함 약 15초)
python -m scripts.run_once --top async_fifo_tb --label ok --files <소스들>
python -m scripts.run_once ... --sim-timeout 10 # 타임아웃 케이스
python -m scripts.collect_xsim_samples [이름]    # xsim 샘플 (이름 생략 시 전부)
```