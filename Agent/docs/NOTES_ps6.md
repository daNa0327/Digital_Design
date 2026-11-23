# Phase 6 NOTES: TB Generator + Compile Gate

> RTL Verification AI Agent 개발의 Phase 6 기록.
> 목적: RTL Analyzer 요약(Phase 5)과 RTL 소스로 **LLM이 self-checking TB를 만들고**, 결정적 검사(정적 검사, 컴파일 게이트)로 거른 뒤, 기존 평가 하네스(Phase 4)로 품질을 잰다.
> 작성 기준일: 2026-11-23 / 평가 대상 DUT: sync FIFO (async FIFO는 아직 시도하지 않음)

상태 표기: ✅ 확인됨 · ⚠️ 부분 확인/추정 · ❓ 미확인(가설) · ⏸ 보류

---

## 1. 구조

```
rtl_summary(JSON) + RTL 소스 + (선택) spec.md
        │
        ▼
 build_tb_prompt ──▶ LLMClient (캐시 → 호출 상한 → 속도/일일 한도 → 제공자, 재시도)
        │
        ▼
 extract_verilog ──▶ check_tb (정적 검사, 결정적)
        │                         │ error 있음
        ▼                         ▼
 compile_check (xvlog → xelab) ──▶ 실패 시 문제 목록 + 직전 코드를 담은 수리 프롬프트 ─▶ 재생성 (최대 N회)
        │ 통과
        ▼
 run_eval --tb (골든 PASS + 변형 19개) ──▶ compare_eval (사람 TB와 비교)
```

| 단계 | 파일 | 내용 |
|---|---|---|
| 6-1 | `llm/` (base, fake, cache, limiter, client, gemini, config), `scripts/llm_ping.py` | 제공자 인터페이스, 오류 계층, 디스크 캐시, 속도/일일 한도 제어, 재시도, 호출 상한, Gemini 제공자, `.env` 설정 |
| 6-2 | `core/tb_prompt.py`, `core/tb_check.py`, `core/tb_generator.py`, `scripts/gen_tb.py`, `dut/sync_fifo/spec.md` | 프롬프트 생성, 응답에서 코드 추출, TB 정적 검사, 1회 생성 |
| 6-3 | `core/compile_gate.py`, `core/tb_repair.py` | xvlog/xelab 게이트, 에러 되먹임 재시도 루프 |
| 6-4 | `scripts/run_eval.py`(`--tb`), `core/eval_compare.py`, `scripts/compare_eval.py` | 같은 변형 세트로 임의 TB 평가, 두 TB 결과 비교 |

---

## 2. 6-1: LLM 계층

### 2.1 설계

| 요소 | 내용 | 이유 |
|---|---|---|
| `LLMProvider` 인터페이스 | `generate(LLMRequest) -> LLMResponse` 하나. 제공자는 Gemini와 테스트용 `FakeLLM` | 모델이나 제공자를 바꿔도 Agent 코드는 그대로 |
| 오류 계층 | `LLMError` ← `LLMTransientError` ← `RateLimitError(retry_after)`, `DailyQuotaExceeded`, `BudgetExceeded`, `BillingRequired` | 재시도할 오류(일시적)와 즉시 중단할 오류(일일 한도, 결제)를 코드로 구분 |
| 디스크 캐시 | 제공자, 모델, 프롬프트, system, 온도, 출력 상한의 sha256이 키. 깨진 파일은 미스로 처리 | 같은 입력을 다시 돌려도 호출 한도를 쓰지 않음 (실제로 6-3 재실행에서 확인) |
| `RateLimiter` | 분당 호출 수 대기, 일일 호출 수를 디스크에 저장 (태평양 자정 초기화) | 무료 한도 보호. 설정 상한(RPM 12, RPD 450)은 표시 한도(15/500)보다 보수적 |
| `LLMClient` | 캐시 → 호출 상한 → 한도 제어 → 제공자 → 재시도(`retry_after` 또는 지수 백오프). 캐시 적중은 한도와 상한을 쓰지 않음 | 개발 중 실수로 호출을 쏟아붓는 것 방지 |
| 설정 | `.env`(Git 제외)의 `GEMINI_API_KEY`, `RVA_LLM_*`. 셸 환경 변수가 `.env`보다 우선 | 키가 저장소에 들어가지 않음. `.env.example`만 커밋 |

### 2.2 확인된 사실

| 사실 | 상태 | 비고 |
|---|---|---|
| Claude Pro 구독에는 API가 포함되지 않음, Google AI 구독도 API 키 사용량을 포함하지 않음 | ✅ (공식 문서 검색) | "구독 사용량을 안 쓰는 API"가 필요해 Gemini 무료 티어를 선택 |
| `--list-models`는 성공하는데 호출이 402를 반환한 적이 있음 | ✅ | 키는 정상이고 호출 단계에서 결제/크레딧 문제 |
| 402는 프리페이 크레딧이 없는 프로젝트의 요청에 대한 응답 | ✅ (공식 문서) | 한도 초과(429)와 구분됨 |
| 프로젝트를 무료 등급으로 전환한 뒤 호출이 성공함 (`gemini-3.5-flash-lite`) | ✅ | 정확한 원인(결제 연결 상태 vs 무료 티어 미적용)은 더 좁히지 못함 ⚠️ |
| 무료 티어의 입력은 제품 개선에 쓰일 수 있음 | ⚠️ (검색 결과, 정책은 바뀔 수 있음) | 본인이 만든 포트폴리오 RTL만 사용. 학교 과제 원본, 연구실, 기업 코드는 넣지 않음 |
| 결제를 다시 연결하면 같은 문제가 재발할 수 있음 | ⚠️ | 크레딧 충전 없이 무료 등급 유지 |

### 2.3 이번 단계에서 생긴 변경

- 402를 `BillingRequired`로 분리하고 재시도하지 않게 함 (안내 문구에 AI Studio Projects 페이지의 Billing Tier 확인을 넣음).
- `.env` 로더는 공백, 따옴표, 주석, `export`, BOM을 허용. 이미 있는 환경 변수는 덮어쓰지 않음.

---

## 3. 6-2: TB Generator

### 3.1 역할 분담

| 구분 | 담당 | 내용 |
|---|---|---|
| 사실 추출 | 코드 (결정적) | 포트, 폭, 클럭, 리셋 극성, timescale 규칙. 프롬프트에 "authoritative"로 박아 LLM이 추측하지 못하게 함 |
| 기대 동작 모델링, 자극 설계 | LLM | 참조 모델, 경계 조건, 랜덤 구간 |
| 규약 준수 확인 | 코드 (`check_tb`) | 아래 3.3 |
| 검증력 평가 | 하네스 (6-4) | 골든 PASS, mutation score |

요약 JSON에는 설계 **의도**가 없고 인터페이스 사실만 있다. 동작 의도는 RTL 소스 또는 명세(`--spec`)에서 LLM이 읽는다.

### 3.2 프롬프트 계약(요약)

단일 ```verilog 블록 / 모듈 `tb_<top>`(포트 없음) / Verilog-2001만 / 이름 기반 포트 연결 / timescale 규칙(없으면 쓰지 않음, 있으면 첫 줄에 동일하게) / 클럭 생성 규칙 / 입력은 negedge, 비교는 posedge+2 / 참조 모델과 `!==` 비교 / 로그 규약 / `$finish`와 워치독 / 금지 태스크 / 고정 seed / 자극 계획 / `// ASSUMPTIONS:` 주석.

변수 선언은 모듈 수준(이름 없는 블록 안 금지), 계약 7의 예외(정의되지 않은 출력은 valid 플래그로 비교를 막고 기대값을 추측으로 초기화하지 않음), 계약 11의 `$random` 부호 주의(`({$random(seed)} % 10) < 8`)는 6절의 실측에서 나온 보강이다.

로그 규약: `$timeformat(-9, 0, " ns", 0)` 1회, 불일치마다 `CHECK_FAIL t=%0t sig=<포트> exp=%0h got=%0h`(최대 10), `CHECKS total=%0d mismatches=%0d`, 마지막에 `[TB] PASS` 또는 `[TB] FAIL: ...` 한 줄. `[TB]` 접두는 이 두 줄 전용.

### 3.3 정적 검사 규칙 (`core/tb_check.py`)

| 수준 | 코드 | 내용 |
|---|---|---|
| error | `no_code`, `no_module`, `unbalanced_module`, `multiple_modules` | 코드 없음, module/endmodule 불일치(잘림), 모듈 둘 이상 |
| error | `tb_has_ports`, `tb_name_clash` | 최상위 TB에 포트, DUT와 같은 이름 |
| error | `systemverilog_construct` | `logic`, `always_ff`, `int`, `bit`, `$urandom` 등 (문자열 안의 단어는 제외) |
| error | `timescale_forbidden/missing/mismatch` | RTL에 없으면 TB에도 금지(XSIM 43-4099), 있으면 같은 값 필요 |
| error | `dut_not_instantiated`, `dut_positional_ports`, `dut_port_missing`, `dut_port_unknown` | DUT 인스턴스와 이름 기반 연결, 빠짐/지어낸 포트 |
| error | `input_undriven` | 입력에 연결된 TB 신호를 구동하는 곳이 없음 |
| error | `no_pass_marker`, `no_fail_marker`, `bad_tb_marker` | `[TB] PASS/FAIL` 규약 |
| error | `no_finish`, `uses_stop`, `uses_error_task`, `uses_dump` | `$finish` 필수, `$stop`/`$fatal`/`$error`/`$dumpfile` 금지 (VCD는 Agent의 Tcl이 생성) |
| warning | `output_unobserved`, `no_case_equality`, `no_watchdog`, `no_check_fail_log`, `no_checks_summary`, `no_random`, `no_timeformat`, `signed_random_modulo`, `fake_error_text`, `dut_multiple_instances` | 검증 품질이 의심되거나 리포트 정보가 빠지는 경우 |

### 3.4 확인된 사실

| 사실 | 상태 | 비고 |
|---|---|---|
| 직접 쓴 `tb_sync_fifo_sc.v`는 error 0개 (워치독 경고 1개) | ✅ | 검사기가 현실과 어긋나지 않는다는 근거 (테스트로 고정) |
| 원래의 눈으로 보는 `tb_sync_fifo_ref.v`는 마커 없음과 timescale 충돌로 거부됨 | ✅ | 테스트로 고정 |
| 첫 LLM 생성물은 정적 검사를 통과했지만 컴파일에서 실패함 | ✅ | 아래 4절. 정적 검사는 "돌려볼 가치"만 거름 |
| Windows에서 `write_text`가 `\r\n`을 만들어 소스 비교 테스트가 실패함 | ✅ 수정 | `load_sources`가 해시는 원본 바이트로 검증하고 프롬프트 텍스트는 `\n`으로 통일 (OS가 달라도 같은 프롬프트와 캐시 키) |
| `spec.md`를 README와 분리해야 함 | ✅ | README에는 사람 TB의 시나리오 목록이 있어 LLM이 베낄 수 있음. `spec.md`는 동작 표만 담고, full/empty 설명은 `fifo_ctrl.v`와 대조해 작성 |

---

## 4. 6-3: Compile Gate와 수리 루프

### 4.1 설계

| 항목 | 결정 | 이유 |
|---|---|---|
| 단계 | `xvlog` → `xelab` (xsim은 돌리지 않음) | 문법뿐 아니라 모듈/포트 해석 오류도 결정적이고 몇 초면 확인됨 |
| 모드 | 기본 Verilog(`-sv` 없음), `--sv`로 평가 흐름과 같은 조건 선택 가능 | 계약이 Verilog-2001이고 v1 범위가 Verilog. 아래 4.2 |
| TB 파일 | 받은 코드를 머리말 없이 그대로 씀 | 에러 줄 번호가 LLM이 본 코드와 일치 (저장본은 머리말 2줄 때문에 2줄 밀림) |
| 에러 | `ERROR: [코드] 메시지 [파일:줄]`을 구조화. "ignored due to previous errors" 등 파생 에러는 `primary=False` | 되먹임에는 원인만 사용 |
| 되먹임 | 정적 error와 컴파일 에러를 한 번에 모아 (최대 8개), 에러 줄의 코드와 에러 코드별 힌트를 붙여 "전체 수정본"을 요구 | 라운드 수 절약 |
| 건너뜀 | 코드 없음, 잘림(`MAX_TOKENS`), 괄호 불일치는 컴파일하지 않음 | 잘린 코드의 에러는 잡음 |
| 한도 | 기본 최대 3회 (시도마다 LLM 1회, 컴파일은 호출 없음) | 무료 한도 보호 |
| 도구 없음 | `FileNotFoundError`를 그대로 올림 | TB 문제가 아니라 환경 문제 |

### 4.2 실측과 발견

| 사실 | 상태 | 비고 |
|---|---|---|
| 첫 생성 TB가 `VRFC 10-8885: declarations are not allowed in an unnamed block`(이름 없는 블록 안의 `reg` 선언)로 xvlog에서 실패 | ✅ | 정적 검사가 못 잡은 문제를 게이트가 잡음 |
| 게이트가 에러 줄 번호(코드 기준 101행)와 해당 코드를 되먹임에 실었고, 2번째 시도에서 통과 | ✅ | 시도 1은 캐시, 실제 호출은 그 실행에서 1회 |
| 평가 흐름(`xvlog -sv`, README 기준)에서는 이 TB가 통과했을 가능성이 있음 | ⚠️ | `sim/xsim.py`를 직접 확인하지는 않음. Verilog 모드를 기본으로 한 선택의 대가는 호출 1회 |
| 실제 Vivado 테스트 3개(이름 없는 블록 선언 실패, 최소 TB 통과, 사람 TB의 `-sv` 통과) 통과 | ✅ | 사용자 환경 pytest 365 passed |

---

## 5. 6-4: 평가와 비교

- `run_eval --tb <파일> --label <이름>`: TB top을 코드에서 읽고(`--tb-top`으로 덮어쓰기 가능) 같은 골든과 변형 19개로 평가. 결과는 `runs/tbeval_<label>_<시각>/`.
- 접두를 `tbeval_`로 한 이유: `make_baseline_report`가 `runs/eval_*`의 최신을 기준선으로 쓰므로 LLM 평가가 기준선 리포트를 덮어쓰지 않게 하기 위함.
- `compare_eval`: 한쪽만 잡은 변형, 둘 다 못 잡은 변형, 첫 불일치 시각, **CHECK_FAIL 없이 FAIL로 잡힌 변형**(워치독 타임아웃 등)을 따로 표시.
- 결과 JSON에 TB 경로, top, sha256을 기록 (어떤 TB로 낸 점수인지 추적).

---

## 6. 실측 결과 (sync FIFO, 온도 0, 샘플 3개)

| 항목 | 사람 TB (기준선) | LLM 샘플 1 | LLM 샘플 2 | LLM 샘플 3 (프롬프트 보강 후) |
|---|---|---|---|---|
| 정적 검사 / 컴파일 게이트 | - | 통과 (2번째 시도) | 통과 (2번째 시도) | 통과 (**1번째 시도**) |
| **골든** | PASS | **PASS** | **FAIL** (거짓 실패) | **PASS** |
| detected / survived / invalid | 17 / 0 / 0 | 17 / 0 / 0 | 평가 중단 | 17 / 0 / 0 |
| 동등 변형 (정상 생존) | 2 | 2 | - | 2 |
| **mutation score** | **100%** | **100%** | 측정 불가 | **100%** |
| 첫 불일치 시각 | 27~417 ns | 읽지 못함 (`$timeformat` 누락) | - | 27~637 ns |
| LLM 호출 | 0 | 2 | 2 | 1 |

**골든 PASS율은 3회 중 2회다** (프롬프트 보강 전 2회 중 1회, 보강 후 1회 중 1회). 정적 검사와 컴파일 게이트를 모두 통과해도 골든에서 FAIL하는 TB가 나왔다는 반례는 그대로 남는다. 보강 후 1회 성공은 효과의 증거가 아니라 "깨지지 않았다" 수준이다 (n=1).

샘플 3에서 확인된 것: ① `$timeformat` 보강이 동작해 첫 불일치 시각을 읽는다 (27~637 ns). ② 컴파일 게이트를 첫 시도에 통과했다 (선언 위치 규칙의 효과일 수 있으나 n=1). ③ 사람 TB의 최대값(417 ns)보다 늦게 잡힌 변형이 B03(567 ns), B04(597 ns), B17(637 ns)로 세 개 있다. 이 변형들은 사람 TB에서 모두 417 ns 이내에 잡혔으므로 샘플 3이 해당 상황(두 포인터가 동시에 움직이는 구간, 7개 찬 상태의 동시 동작)에 더 늦게 도달한다. 원인은 방향성 시나리오가 늦거나 랜덤 구간에서 처음 만나기 때문일 수 있다 ⚠️ (샘플 3의 코드는 리뷰하지 않았다).

### 6.1 샘플 1: 점수가 100%여도 구분력이 없다

- **점수가 100%로 같다는 것은 두 TB가 같은 품질이라는 뜻이 아니다.** 변형 19개가 모두 한 줄 치환 단일 버그라 이 세트로는 두 TB를 구분할 수 없다 (천장 효과).
- 수리 전 첫 생성물을 코드로 읽어 본 약점 (시뮬레이션으로 확인한 것은 아님): 랜덤 확률 왜곡, 랜덤 구간이 하나뿐, 방향성 시나리오의 COVER를 손으로 증가, 참조 모델이 RTL의 게이팅 구조를 따라 함, 리셋이 클럭 에지 두 개에 걸쳐 유지되어 "비동기 리셋이 동기 리셋으로 바뀐" 변형이 구분되지 않을 가능성.
- **샘플 1 수리본(`sync_fifo_llm_gated.v`)의 코드는 리뷰하지 않았다.** 위 약점이 남아 있는지, 골든 PASS가 `data_out` 기대값을 초기화하지 않은 덕(X와 X는 `!==`로 같음)인지 확인하지 못했다 ⚠️.

### 6.2 샘플 2: 골든 FAIL의 원인 (재현으로 확인)

샘플 2 수리본 `sync_fifo_llm_gated2.v`를 Icarus Verilog로 골든 DUT와 돌려 재현했다.

| 확인 | 결과 |
|---|---|
| 불일치 | 10건 전부 `sig=data_out exp=0 got=xx` (`CHECKS total=656 mismatches=10`) |
| 원인 | TB가 `reg [7:0] ref_data_out = 8'h00;`으로 기대값을 0으로 초기화했는데, DUT의 `data_out`은 첫 read 전까지 X (`fifo_mem`의 출력 레지스터에 초기값도 리셋도 없음). `X !== 0`이라 첫 read 이전의 비교 10회가 모두 불일치 |
| 확인 실험 | 그 한 줄만 `reg [7:0] ref_data_out;`(X)로 바꾸면 `mismatches=0`, `[TB] PASS` |
| 나머지 | 참조 모델, 타이밍, 로그 규약은 맞았다. 같은 TB가 이 한 줄 때문에 거짓 실패한 것 |

**프롬프트와 명세 쪽 책임이 있다.** 계약 7번이 "`!==`로 비교해 X도 불일치로 본다"고 요구했고, 명세(`spec.md`)에는 "첫 read 전 `data_out`은 정의되지 않음"이 없었다. 사람 TB는 `m_dout_valid` 플래그로 이 구간을 건너뛰는데, LLM에게는 그 정보가 주어지지 않았다.

### 6.3 샘플 2의 추가 관찰 (코드 리뷰 + Icarus 실측)

| 관찰 | 근거 |
|---|---|
| `($random(seed) % 10) < 8`은 의도한 80%가 아니라 **90%**, `< 3`은 의도한 30%가 아니라 **65%** | Icarus로 100,000회 측정. `$random`이 부호 있는 값이라 음수 나머지가 모두 참 |
| 랜덤 구간이 3개로 나뉘었지만 위 왜곡 때문에 "쓰기 우세 / 읽기 우세"가 아니라 90/65, 65/90에 가깝다 | 위와 같음 |
| 리셋은 full 상태에서 걸었다 (샘플 1의 약점 하나 해소) | 코드 |
| 리셋이 클럭 에지 두 개 이상에 걸쳐 유지되어 비동기/동기 리셋 구분이 안 된다 | 코드 |
| 참조 모델이 RTL의 `mem_wr_en`/`mem_rd_en` 게이팅 구조를 그대로 따랐다 | 코드 |
| 두 샘플 모두 첫 시도에서 "이름 없는 블록 안의 선언"으로 컴파일 실패 | 게이트 출력 (같은 실수가 반복됨) |

### 6.4 발견한 결함 두 가지와 조치

1. **첫 불일치 시각이 전부 `None`**: 프롬프트 규약에 `$timeformat`이 빠져 LLM TB가 단위 없는 시각을 출력했고 하네스는 단위가 없으면 읽지 않는다. 점수에는 영향이 없다. 규약에 추가하고 정적 검사에 `no_timeformat` 경고를 추가했다.
2. **골든 FAIL (6.2)**: 아래를 수정했다.
   - `spec.md`에 "첫 read 전의 `data_out`은 정의되지 않음(X), 비교 대상이 아님"을 추가 (RTL과 시뮬레이션으로 확인한 사실이며 사람 TB의 시나리오가 아니다).
   - 계약 7에 예외 추가: 명세나 RTL에서 정의되지 않은 출력은 valid 플래그로 비교를 막고 기대값을 추측으로 초기화하지 않는다. 이 규칙은 명세 없이 RTL만 줄 때도 적용되도록 "reset/initial이 없는 출력 레지스터" 예를 들었다.
   - 계약 11에 `$random` 부호 주의와 올바른 관용구 추가, 계약 2에 "이름 없는 블록 안에 선언하지 말 것" 추가.
   - 정적 검사에 `signed_random_modulo` 경고 추가 (직접 쓴 TB의 `{$random(seed)} % N`은 경고하지 않음).

위 수정의 효과는 샘플 3으로 1회 확인했다 (골든 PASS, 첫 시도 컴파일 통과). n=1이라 통계는 아니며, 반복 생성으로 골든 PASS율 분포를 재야 한다 (8절).

## 7. 한계와 주의

| 항목 | 내용 |
|---|---|
| 의도 파악 | 요약에는 의도가 없다. RTL만 주면 RTL의 버그를 정상 동작으로 모델링할 수 있다. 명세(`--spec`)가 있을 때 신뢰도가 높다 |
| 정적 검사 | 정규식 기반이라 특이한 문법(generate 안의 인스턴스 등)은 놓치거나 오탐할 수 있다. 최종 판단은 컴파일 게이트 |
| 통과 단계와 골든 PASS | 정적 검사와 컴파일 게이트를 통과해도 골든에서 FAIL할 수 있다 (실제 사례, 6.2). 두 검사는 "돌려볼 가치"만 거른다 |
| 평가 세트 | sync FIFO 1개, 변형 19개(단일 버그). 점수가 포화되어 변별력이 없다 |
| LLM 비결정성 | 온도 0 + 캐시라 같은 입력은 같은 결과지만, 다른 프롬프트나 모델에서는 다를 수 있다 |
| 무료 티어 | 한도와 정책은 바뀔 수 있다. 입력이 제품 개선에 쓰일 수 있어 민감한 코드는 넣지 않는다 |
| 샘플 수 | 3개뿐이다 (같은 프롬프트로는 1개). 골든 PASS율 2/3은 통계가 아니라 "실패할 수 있다"는 반례 이상의 의미가 없다. 온도 0과 캐시 때문에 같은 명령을 반복해도 같은 결과라 분산을 재려면 별도 방법이 필요하다 |
| 다중 클럭 | 프롬프트에 다중 클럭 규칙은 있지만 async FIFO로는 아직 한 번도 돌려 보지 않았다 ❓ |

---

## 8. 보류 / 다음 후보

| 항목 | 상태 | 내용 |
|---|---|---|
| 골든 게이트(6-5 후보) | ⏸ | 컴파일 게이트처럼 TB를 골든 DUT에서 xsim으로 한 번 돌려 FAIL이면 CHECK_FAIL 줄을 되먹여 재생성. 비용은 몇 초이고 LLM 호출만 추가. **주의: 골든의 동작을 TB에 반영하게 되므로 RTL 버그가 TB에 굳을 수 있다.** 평가에서는 "되먹임 없는 첫 생성의 골든 PASS율"을 정직한 지표로 따로 기록하고, 실제 사용(정답을 모르는 RTL)에서는 FAIL이 TB 오류인지 RTL 버그인지 구분할 수 없으므로 자동 수정하지 않고 Phase 7의 판단 대상으로 넘겨야 한다 |
| 반복 생성 평가(6-5 후보) | ⏸ | 온도를 올리고 캐시를 끄고 N회(예: 5) 생성해 첫 시도 컴파일 통과율, 재시도 포함 컴파일 성공률, **되먹임 없는 골든 PASS율**, 골든 PASS인 샘플의 mutation score 분포를 잰다. README 지표 표의 값을 실측으로 채우는 단계. 호출은 샘플당 1~3회, Vivado는 골든 확인 샘플당 수 초 + 통과한 샘플의 변형 평가 2~4분 |
| 더 어려운 변형 세트 | ⏸ | 비동기→동기 리셋, 리셋 시 `data_out` 삭제, full 상태에서의 리셋, 두 버그 동시 주입 등. 점수 포화를 풀어 TB 품질을 구분하기 위함 |
| 반복 생성(분산 측정) | ⏸ | 같은 DUT에서 여러 번 생성해 골든 PASS율과 점수의 분포를 본다. 호출량은 DUT당 수 회 |
| async FIFO(다중 클럭) 생성 | ⏸ | 가장 약할 것으로 예상되는 경우. `empty` 비대칭 의심(Phase 3 보류 항목)과 함께 확인 |
| 게이트의 xelab 기본 timescale 옵션 | ⏸ | timescale이 일부 모듈에만 있는 DUT는 아직 `blockers`로 거부 |
| baseline 리포트의 "불일치 수" 열 | ⏸ | TB는 사이클당 검사 수를 세고 불일치는 신호별로 세서 불일치 수가 검사 수보다 클 수 있음. 열 이름 변경 안(불일치 신호 수 / 비교 사이클 수)은 아직 미적용 |
| README의 v2-a / v2-b 분리 | ⏸ | 미적용 |
| `requirements.txt` | 확인 필요 | `google-genai`, `tzdata`를 추가했는지 확인 |

---

## 9. 명령어 요약

```powershell
cd C:\Users\Junyoung\Desktop\Verilog\Agent
.\.venv\Scripts\Activate.ps1

pytest -q                                                # 389 passed 기대

# LLM 연결 확인
python -m scripts.llm_ping --list-models
python -m scripts.llm_ping

# TB 생성
python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --spec dut/sync_fifo/spec.md --dry-run
python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --spec dut/sync_fifo/spec.md --gate --out runs/tb/sync_fifo_llm_gated.v
python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --check runs/tb/sync_fifo_llm_gated.v --compile

# 수정한 프롬프트로 다시 생성해 세 번째 샘플 만들기 (같은 DUT, 새 프롬프트라 새 샘플)
python -m scripts.gen_tb dut/sync_fifo/rtl --top sync_fifo --spec dut/sync_fifo/spec.md --gate --out runs/tb/sync_fifo_llm_gated3.v
python -m scripts.run_eval --tb runs/tb/sync_fifo_llm_gated3.v --label llm3

# LLM TB 평가와 비교 (Vivado만 사용, 약 4분)
python -m scripts.run_eval --tb runs/tb/sync_fifo_llm_gated.v --label llm
python -m scripts.compare_eval runs\eval_<시각>\results.json runs\tbeval_llm_<시각>\results.json --label-a human --label-b llm
```

## 10. 테스트 수

| 파일 | 개수 | 내용 |
|---|---|---|
| `test_llm_core.py`, `test_llm_limiter.py`, `test_llm_config_gemini.py` | 53 | 6-1 (402 매핑 포함) |
| `test_tb_check.py` | 48 | 추출, 정적 검사 규칙, 실제 사람 TB 대조 |
| `test_tb_prompt.py` | 26 | 프롬프트 내용, 요약 거부, 소스 로더(CRLF 포함) |
| `test_tb_generator.py` | 16 | 생성, 잘림, 캐시, 저장 |
| `test_compile_gate.py` | 24 | 파서, 단계 조율(가짜 도구), 실제 Vivado 3개 |
| `test_tb_repair.py` | 18 | 되먹임, 한도, 건너뜀 조건 |
| `test_gen_tb_cli.py` | 4 | `--dry-run`, `--check`, `--gate` |
| `test_eval_compare.py` | 17 | 비교 계산, 리포트, `--tb` 인자 해석 |
| 합계 | 206 | Phase 5까지 183개 + 206개 = 389개 |

## 11. 후속 설계 메모: 통합 실행 (Phase 8)

사용자가 `dut/<이름>/`에 RTL과 spec을 넣고 `run_agent.bat`만 실행하면 리포트가 나오는 구조로 설계했다. 상세는 README "최종 사용 방법". 요점만 남긴다.

- bat는 얇게(환경 설정, 인자 선택, 호출, 결과 열기), 로직은 `scripts/run_agent.py`에 둔다. Python은 pytest로 고정하고 bat는 직접 실행으로 확인한다.
- 모드: `verify`(골든 없음, 변형 평가 없음) / `eval`(골든 + 변형).
- 사전 점검에서 예상 호출 수와 오늘 남은 호출 수를 비교해 시작 전에 중단한다.
- 중간 실패에도 리포트는 만든다.
- ⚠️ `.gitignore`의 `*.bat` 때문에 bat가 커밋되지 않는다. 8-3에서 `!run_agent.bat` 예외를 추가한다.