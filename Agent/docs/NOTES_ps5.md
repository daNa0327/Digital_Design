# Phase 5 NOTES: RTL Analyzer

> RTL Verification AI Agent 개발의 Phase 5 기록.
> 목적: Verilog 소스에서 **LLM 없이 결정적으로** DUT 정보(모듈, 포트, 파라미터, 계층, 클럭/리셋, timescale)를 뽑고, TB Generator(Phase 6)에 넘길 요약 JSON으로 묶는다.
> 작성 기준일: 2026-11-23 / 검증 대상 DUT: sync FIFO (모듈 3개), async FIFO (모듈 5개)

상태 표기: ✅ 확인됨 · ⚠️ 부분 확인/추정 · ❓ 미확인(가설) · ⏸ 보류

---

## 1. 구조

```
.v 파일들 ─▶ strip_comments ─▶ parse_modules ─▶ [Module...]
                                   │  (포트, 파라미터, 인스턴스, 클럭/리셋, timescale)
                                   ▼
                           build_hierarchy ─▶ Hierarchy (top 후보, 자식, 연결 점검, timescale 상태)
                                   ▼
                           top_interface ─▶ top 포트 기준 클럭/리셋 (자식에서 전파)
                                   ▼
                           summarize_* ─▶ 요약 dict ─▶ validate_summary
```

| 단계 | 파일 | 내용 |
|---|---|---|
| 5-1 | `core/rtl_analyzer.py` | 주석 제거, 모듈 분리, ANSI 포트와 파라미터 추출, 정수 식 계산 |
| 5-2 | `core/rtl_analyzer.py` | 인스턴스 추출, 계층, top 추정, 포트 연결 점검 |
| 5-3 | `core/rtl_clkrst.py` (+ `rtl_analyzer.py`) | always 블록 기반 클럭/리셋 판별, timescale, top 인터페이스 전파 |
| 5-4 | `core/rtl_summary.py` | 요약 dict 생성, 스키마 검증, TB 생성 차단 조건 |
| CLI | `scripts/show_rtl.py`, `scripts/make_rtl_summary.py` | 사람이 보는 표, JSON 요약 |
| 테스트 | `tests/test_rtl_analyzer.py` (24), `test_rtl_hierarchy.py` (18), `test_rtl_clkrst.py` (21), `test_rtl_summary.py` (22) | 85개 |

`core/analyzer.py`는 시뮬레이션 **로그 판정**용이라 이름이 겹치지 않도록 RTL 쪽은 `rtl_` 접두사를 썼다.

## 2. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 파서 | 직접 만든 경량 파서 (주석 제거 후 문자열 처리) | 외부 파서 의존성 없음, 동작을 테스트로 고정 가능. 외부 도구(Verilator, Yosys 등) 사용은 검토만 하고 채택하지 않음 (⏸) |
| 지원 범위 | ANSI 포트, `always @(...)`, 이름/위치 연결 인스턴스 | 목표 DUT 스타일. 범위 밖 구문은 **추측하지 않고 경고** |
| 주석 처리 | 주석을 공백으로 치환 (문자 수와 줄바꿈 유지) | 줄 번호가 원본과 일치. 문자열 안의 `//`는 주석이 아님 |
| 폭 계산 | 정수 식만 계산 (`+ - * / % << >>`, `$clog2`, 파라미터 대입). 못 하면 `width=None` + 경고 | 틀린 값을 LLM에 넘기는 것보다 모른다고 하는 편이 안전 |
| top 추정 | 어떤 모듈도 인스턴스화하지 않는 모듈. **후보가 정확히 하나일 때만** `best_top` | 여럿이면 고르지 않고 경고 |
| testbench | 포트가 없고 인스턴스가 있는 모듈. TB가 부르는 모듈은 "사용됨"으로 치지 않음 | RTL과 TB를 함께 줘도 DUT가 top 후보로 남음 |
| 연결 점검 | `unknown_port`, `unconnected`, `too_many_positional` | 앞의 둘 중 `unknown_port`, `too_many_positional`은 컴파일이 실패할 오류라 TB 생성 차단 사유. `unconnected`는 정보 |
| 클럭/리셋 | 감도 목록의 에지 + 첫 `if` 조건 + 이름. `evidence`로 근거 강도 기록 | 이름만으로 판단하지 않음. 모호하면 분류하지 않고 경고 |
| 리셋 극성 | 비동기는 에지(posedge=high, negedge=low)가 기준, if 조건 극성과 어긋나면 경고 | 에지는 구조적 사실, 이름은 관례 |
| 전파 | top에 always가 없어도 `.port(top_port)` 단순 연결을 따라 자식의 클럭/리셋을 top 포트로 전파 | async FIFO의 top은 순수 구조 모듈 |
| 요약의 경계 | `blockers`(TB 생성 불가), `notes`(영향 있음), `warnings`(분석 경고 원문) 분리 | Phase 6가 "되돌려야 하는지"를 코드로 판단 |
| 요약 검증 | `validate_summary()`가 스키마, 참조 일관성, `ready_for_tb == (blockers 없음)`을 검사 | LLM 입력이 깨진 채 넘어가지 않게 |
| 재현성 | 요약은 결정적이고 `sources`에 파일 해시(12자리) 기록 | 입력이 같은지 확인, 캐시 키로 사용 가능 |

### 클럭/리셋 판별 규칙

| evidence | 조건 | 강도 |
|---|---|---|
| `sensitivity+if` | 감도 목록 에지 신호가 둘이고, 하나를 첫 `if`가 검사 (예: `posedge reset` + `if (reset)`) | 강함 |
| `sensitivity+name` | 에지 신호가 둘이고 이름(rst/reset/clr/clear)으로만 구분 | 중간 |
| `if+name` | 에지가 하나인 블록의 첫 `if`가 리셋 이름 신호를 검사 (동기 리셋) | 약함 |
| (분류 안 함) | 두 신호 모두 단서 없음, 에지 3개 이상, 레벨 감도(조합 논리) | 경고 또는 무시 |

### TB 생성 차단 조건 (`blockers`)

top을 정하지 못함 / top 포트 폭을 계산하지 못함 / 비ANSI top 포트 / 설계 안의 정의 없는 모듈 / 포트 연결 오류 / **timescale이 일부 모듈에만 있음**.

그 외 (클럭 없음, 리셋 없음, 다중 클럭, 약한 리셋 근거, 모듈별 timescale 값 차이)는 `notes`로 남기고 막지 않는다. 클럭이 없는 순수 조합 회로(예: `bin2gray`)도 정상 DUT이기 때문이다.

## 3. 측정과 발견 (실제 DUT 출력으로 확인)

### 3.1 sync FIFO ✅

| 항목 | 값 |
|---|---|
| 모듈 | `sync_fifo`(top), `fifo_ctrl`(c1), `fifo_mem`(m1). 연결 문제 0건, 경고 0건 |
| 클럭 | `ck` (posedge), 단일 클럭 |
| 리셋 | `reset`, 비동기 active-high, 근거 `sensitivity+if` |
| timescale | 없음 (설계 기준 `none`) → TB 지시문은 빈 문자열 |

### 3.2 async FIFO ✅

| 항목 | 값 |
|---|---|
| 모듈 | `async_fifo`(top), `fifo_ctrl`(c1), `fifo_mem`(m1), `bin2gray`, `synchronizer` |
| 인스턴스 연결 수 | `fifo_ctrl` 9, `fifo_mem` 8, `bin2gray` 2, `synchronizer` 4 (각 모듈의 포트 수와 일치, 미연결 포트 0) |
| 클럭 | `wr_ck`, `rd_ck` (둘 다 posedge) → `multi_clock: True` |
| 리셋 | `reset`, 비동기 active-high, 근거 `sensitivity+if`. `fifo_ctrl`에서 2개 블록(쓰기/읽기 도메인)과 `synchronizer`가 사용 |
| timescale | **모든 모듈 `1ns/1ps`** (설계 기준 `all`) → TB 지시문은 `` `timescale 1ns/1ps `` |
| 계층 | `fifo_ctrl` 아래에 `bin2gray` 3개(wr_gray1, rd_gray1, wr_gray2)와 `synchronizer` 2개(sync_rd2wr, sync_wr2rd) |

### 3.3 두 DUT의 timescale이 서로 다르다 ✅

sync FIFO는 timescale이 없고 async FIFO는 `1ns/1ps`다. Phase 4에서 XSIM 43-4099로 확인했듯이 TB와 RTL의 timescale 유무가 어긋나면 elab에서 실패한다. 그래서 **TB의 timescale 지시문은 DUT마다 달라야 하고**, 이 값을 LLM이 추측하게 두지 않고 요약의 `timescale.tb_directive`로 코드가 정해 준다.

| 설계 timescale 상태 | `tb_directive` | 의미 |
|---|---|---|
| `none` | `""` | TB에도 쓰지 않는다 |
| `all` | `` `timescale <top의 값> `` | TB에 그 값을 쓴다 |
| `mixed` | `None` + blocker | 어떤 TB로도 xelab이 실패하므로 RTL 수정 또는 xelab 기본 timescale 옵션이 필요 (옵션 사용은 미구현 ⏸) |

### 3.4 관찰 (확정이 아닌 단서) ⚠️

- `fifo_ctrl`에서 `bin2gray`가 write 쪽 2개(`wr_gray1`, `wr_gray2`), read 쪽 1개(`rd_gray1`)로 비대칭이다. 이전부터 보류 중인 async FIFO `empty` 비대칭 의심과 관련된 단서일 수 있다. 소스 로직을 비교하지 않았으므로 **확정된 것이 아니다**.
- 리셋 `reset`이 두 클럭 도메인과 동기화기에 그대로 연결되어 있다 (top 포트에서 직접). 리셋 해제가 각 클럭에 동기화되는 구조는 아닌 것으로 보인다 (⚠️, 소스로 별도 확인 필요). Phase 6의 TB에서는 리셋 해제를 양쪽 클럭 에지에서 떨어뜨려 두는 것이 안전하다.
- 5-2 출력만으로는 `fifo_ctrl.v`의 `full`, `empty`가 어떤 always 블록에서 갱신되는지 알 수 없다. 클럭 판별 결과(`wr_ck` x1, `rd_ck` x1)는 쓰기, 읽기 도메인이 각각 한 블록임을 보여 준다.

## 4. 검증 결과

### 4.1 자동 테스트

| 파일 | 개수 | 주요 내용 |
|---|---|---|
| `test_rtl_analyzer.py` | 24 | 주석 제거(길이/줄 보존, 문자열), 정수 식, ANSI 포트, 방향/범위 이어받기, 파라미터, 비ANSI/generate 경고, CRLF, 실제 sync FIFO |
| `test_rtl_hierarchy.py` | 18 | 인스턴스(이름/위치/오버라이드/배열/쉼표), 키워드와 함수 호출 제외, top 추정, testbench 제외, 연결 점검, 트리 출력 |
| `test_rtl_clkrst.py` | 21 | 비동기 high/low 리셋, 순서 무관, 이름 근거, 모호 경고, 극성 불일치, 동기 리셋, 조합 논리 무시, timescale 상태, 전파, 실제 DUT |
| `test_rtl_summary.py` | 22 | 요약 필드, 결정성, JSON 왕복, 차단/참고 조건, 스키마 위반 감지, CLI, 실제 DUT |

모든 테스트에 한글 docstring을 달았다. 전체 기대값은 `98 + 85 = 183`개. 5-3까지 161개는 실행 확인했고, 5-4의 22개는 적용 후 확인이 필요하다 (⚠️).

실제 async FIFO 요약 테스트(`test_async_fifo_summary`)는 5-3 출력으로 확인한 사실(포트 순서와 폭, 클럭, 리셋, timescale, 계층)만 단정한다. 작성 환경에는 async RTL이 없어서 사실에 맞춘 합성 파일로 먼저 검증했고, 실제 파일로의 확인은 사용자 환경에서 한다.

### 4.2 검증 과정에서 고친 것

- 정규식 기반 timescale 정규화에서 f-string 안에 백슬래시를 쓴 코드가 있었는데, Python 3.12 미만에서는 문법 오류가 된다. 일반 코드로 풀었다 (사용자 Python 버전을 모르므로 호환 가능한 형태로).
- testbench 처리: 처음에는 "아무도 부르지 않는 루트 중 포트 없는 것"만 TB로 봐서, RTL과 TB를 함께 주면 DUT가 top 후보에서 빠졌다. TB가 부르는 모듈을 "사용됨"에서 제외하도록 고쳤다.

## 5. 한계 및 미확인

| 항목 | 상태 | 비고 |
|---|---|---|
| 비ANSI 포트 | ⏸ | 지원하지 않고 경고. 필요하면 확장 |
| `generate`, 매크로, `` `include `` | ⏸ | 해석하지 않고 경고 |
| `.*` 와일드카드 연결 | ⏸ | 해석하지 않고 경고 |
| 복잡한 포트 폭 식 (삼항, 함수) | ⏸ | `width=None` + blocker |
| 내부 생성 클럭 (분주기 출력 등) | ⏸ | 포트가 아니면 경고만. top 인터페이스에는 포함하지 않음 |
| 클럭 도메인별 신호 매핑 | ⏸ | 어떤 입출력이 어느 클럭 도메인인지는 아직 모름. Phase 6의 다중 클럭 TB에서 필요해질 수 있음 |
| FSM 추출 | ⏸ | 로드맵의 "FSM 후보"는 이번 단계에 포함하지 않음. 현재 두 DUT에는 상태 머신이 없고, UART/SPI/I2C에서 필요해질 때 추가 |
| 클럭 주기, 리셋 유지 시간 | ❓ | 소스에서 알 수 없는 값. TB 생성 시 기본값 규칙이 필요 |
| 외부 파서와의 비교 | ⏸ | 사용자 DUT 스타일 밖에서는 정확도를 보장하지 않음 |
| 이름 휴리스틱 | ⚠️ | `rst/reset/clr/clear`는 영어 관례. 다른 이름이면 `evidence`가 약해지거나 분류하지 않음 |

## 6. 작업 중 얻은 교훈

- **모르는 것은 모른다고 기록한다.** 폭을 계산하지 못하면 `None`과 경고를 남기고, 두 에지 신호를 구분하지 못하면 분류하지 않는다. LLM에 틀린 사실을 넘기면 TB가 그럴듯하게 틀린다.
- **판단 근거를 값과 함께 저장한다.** 같은 "리셋"이라도 `sensitivity+if`와 `if+name`은 신뢰도가 다르다. 이후 단계가 근거 강도로 행동을 바꿀 수 있다.
- **같은 사실이 DUT마다 다르다.** timescale이 sync FIFO에는 없고 async FIFO에는 있다는 것을 Phase 4의 실패와 이번 측정이 함께 보여 준다. 규칙을 하드코딩하지 않고 소스에서 매번 뽑아야 한다.
- **구조 모듈은 정보를 아래로 위임한다.** top에 `always`가 없어도 클럭/리셋은 자식에 있으므로 연결을 따라 전파해야 top 인터페이스가 나온다.
- **요약에 "되돌릴 조건"을 넣는다.** `ready_for_tb`와 `blockers` 덕분에 Phase 6가 LLM을 호출하기 전에 코드로 중단할 수 있다.

## 7. 다음 단계 (Phase 6: TB Generator + Compile Gate)

| 확인된 사실 | 설계 |
|---|---|
| 요약 JSON에 TB 생성에 필요한 정보가 모여 있음 (`inputs_to_drive`, `outputs_to_observe`, 클럭, 리셋, `tb_directive`) | 이 요약만 LLM 프롬프트에 넣고, DUT 소스는 필요한 경우에만 첨부 |
| TB는 `[TB] PASS` / `[TB] FAIL: ...` 규약을 지켜야 Phase 2 판정이 동작함 | 프롬프트에 규약을 명시하고 Compile Gate 이후 결과로 검증 |
| timescale은 DUT마다 다름 | `tb_directive`를 코드가 TB에 강제 삽입하거나 검사 (LLM이 정하지 않음) |
| 다중 클럭(async FIFO)과 단일 클럭(sync FIFO)이 모두 있음 | 두 DUT 모두에서 평가 |
| 평가 하네스와 기준선이 있음 (sync FIFO: mutation score 100%) | LLM이 만든 TB의 골든 PASS율과 mutation score를 같은 하네스로 측정해 비교 |
| API 키, 모델, 호출 횟수 상한 결정이 필요 | `llm/` 계층에 모델명과 상한을 설정값으로 분리 (기본 후보 Sonnet 5.5) |

| # | 내용 |
|---|---|
| 6-1 | `llm/` 인터페이스와 설정 (모델, 토큰/호출 상한, 재시도), 가짜 LLM으로 테스트 가능하게 |
| 6-2 | 프롬프트와 TB 생성기 (요약 JSON → TB 코드, 규약과 timescale 강제) |
| 6-3 | Compile Gate (xvlog 검사, 실패 시 에러 메시지와 함께 재시도, 최대 N회) |
| 6-4 | 같은 하네스로 평가: 골든 PASS율, mutation score (LLM TB vs 사람 TB 기준선) |

## 8. 명령어 요약

```powershell
cd C:\Users\Junyoung\Desktop\Verilog\Agent
.\.venv\Scripts\Activate.ps1

pytest -q                                                # 183 passed 기대

python -m scripts.show_rtl dut/sync_fifo/rtl             # 모듈/포트/계층/클럭/리셋 표
python -m scripts.show_rtl Manual_test/dut --json        # JSON 전체
python -m scripts.make_rtl_summary dut/sync_fifo/rtl     # TB Generator 입력 요약
python -m scripts.make_rtl_summary Manual_test/dut --out reports/rtl_summary_async_fifo.json
python -m scripts.make_rtl_summary some_dir --top my_top # top을 직접 지정
```