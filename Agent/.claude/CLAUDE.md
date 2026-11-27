# CLAUDE.md — RTL Verification AI Agent (RVA)

> 프로젝트 루트(`Agent/`)에 두고 커밋한다. 개인 환경·계획·진로 관련 내용은 `CLAUDE.local.md`(gitignore)에 있다. 두 파일을 모두 읽는다.
> 이 파일과 실제 코드/NOTES가 다르면 **코드와 `docs/NOTES_ps*.md`가 맞고**, 이 파일을 고친다.

## 1. 작업 규칙

- 한국어로 답한다. 현실적, 구체적, 직설적, 구조적으로. 가능하면 표, 우선순위, 장단점, 추천 순서를 쓴다.
- 이 프로젝트의 핵심 메시지는 "AI로 Verilog를 작성"이 아니라 **"AI로 RTL 검증 프로세스를 자동화"**다.
- 사용자가 기술적으로 틀리게 이해한 내용은 맞다고 하지 말고 "그 부분은 조금 다르게 이해해야 해"로 시작해 (이해한 내용 → 실제 개념 → 차이의 이유 → 짧은 예) 순서로 고친다.
- **결과의 한계를 숨기지 않는다.** Icarus에서만 확인한 것, 가정한 것, 낙관적인 수치, xsim 미확인은 반드시 그렇게 표시한다.
- 확정 표현("이것만 하면 된다")을 쓰지 않고, 모르는 것을 아는 척하지 않는다.
- 단계는 작게 나누고 단계마다 pytest로 확인한 뒤 git 커밋한다. 커밋 전에 diff 요약을 보여준다.
- Phase가 끝나면 (a) 끝난 Phase의 `docs/NOTES_ps<N>.md`를 새로 쓰고 (b) 이전 NOTES와 `README.md`를 갱신한다.
- 코드를 줄 때는 설계 개념 → 구조 → 코드 → 테스트 → 확인 포인트 순으로 설명한다. "완성된 코드 작성해줘"라고 명확히 요청받으면 완성 코드를 바로 준다.
- 에러가 오면: 원인 → 관련 RTL/도구 개념 → 수정 방법 → 수정 코드 → 왜 맞는지 → 검증 방법.

## 2. 환경

- Windows + PowerShell, Python `.venv`
- **Vivado 2024.2 xsim이 주 시뮬레이터**(xvlog → xelab → xsim, VCD). Icarus Verilog + GTKWave는 보조.
- LLM: 무료 티어 Gemini(`llm/` 모듈, 캐시와 레이트리미터 포함). API 비용이 안 드는 쪽을 유지한다.
- **샌드박스에는 Vivado가 없을 수 있다.** xsim 결과는 사용자 PC에서만 확정된다. Icarus 통과가 xsim 통과를 보장하지 않는다(실제로 변수 선언 순서, TB watchdog 시간에서 xsim 전용 문제가 나왔다).

## 3. 프로젝트 개요 (RVA v1)

Agent 버전 로드맵(확정): **v1** Verilog RTL 기능 검증 자동화 → v1.5 최적화 → **v2** SystemVerilog + UVM → v2.5 최적화 → v3 PPA(timing/power) 분석.

### 파이프라인
RTL → RTL 분석 → TB 생성(선택) → 시뮬레이션 → 로그 분석 → 파형(VCD) 분석 → 실패 감지 → 원인 분석 → 수정 제안 → 수정 검증 → Regression → Report

### 디렉터리 (요약)
```
core/     models, 로그 파서, rtl_analyzer, vcd_reader/vcd_tools, bugs(변형 주입), evaluator,
          tb_generator/tb_prompt/tb_check/tb_repair, compile_gate,
          debug_loop/debug_protocol/debug_tools/debug_eval, fix_verify, eval_report/eval_compare
sim/      runner.py(run_tool, 타임아웃/프로세스 트리 종료), xsim 어댑터
llm/      base, client, config, gemini, cache, limiter, fake
scripts/  run_eval, run_debug_eval, verify_fixes, show_proposals, gen_tb, llm_ping,
          compare_eval, make_baseline_report, make_rtl_summary, show_rtl
dut/      sync_fifo/, spi/, uart/, i2c/ (각 rtl/, tb/, spec.md)
bugs/     sync_fifo/bugs.json, spi/bugs.json, uart/bugs.json, i2c/bugs.json (변형 카탈로그)
docs/     NOTES_p0.md ~ NOTES_ps8.md (Phase별 설계·결과 기록)
tests/    pytest (전체 611개가 기대값)
runs/     실행 결과(results.json, work/ 등)
```

### Phase 진행 상태
| Phase | 내용 | 상태 |
|---|---|---|
| 0–3 | 수동 xsim, XsimSim 어댑터, 로그 파서·판정, VCD Reader·Agent 도구 | ✅ |
| 4 | 골든 sync FIFO, 버그 주입, 평가 하네스 | ✅ |
| 5 | RTL Analyzer | ✅ |
| 6 | TB Generator(LLM 첫 도입), Compile Gate, LLM TB 평가 | ✅ |
| 7 | Debug Agent Loop, 7-5 수정안 검증(`rerun_sim`, `check_fix`) | ✅ |
| 8 | 새 DUT로 일반화 확인(SPI → UART → I2C), Regression/Report, 통합 실행(`run_agent.py` + `run_agent.bat`) | 🚧 8-1 진행 중 |

---

## 4. 핵심 설계 사실 (코드를 건드리기 전에 알아야 하는 것)

### 평가(골든 필요)와 실사용(골든 불필요)은 다르다
- `run_eval`, `run_debug_eval`, `verify_fixes`는 **Agent를 측정하기 위한 도구**라서 골든 RTL이 필요하다(버그를 심고 정답과 비교).
- 실사용 모드는 **RTL + spec + (사람이 쓴 TB)** 만 받는다. 판정 기준(오라클)은 골든이 아니라 TB다.
- 따라서 **TB 품질이 Agent 정확도의 상한**이다. TB 없이 Agent가 TB를 생성하는 모드는 신뢰도가 낮고(버그 있는 RTL에서 기대값을 만들면 버그를 정상으로 기대한다), 리포트에 그렇게 명시해야 한다. 기본 모드는 사람이 쓴 TB. 8-3의 `run_agent`는 이 구분을 지킨다.

### Debug Agent
- 한 턴에 JSON 액션 하나. 도구: `read_rtl`, `search_rtl`, `get_log_snippet`, `read_tb`, `list_signals`, `read_vcd_signal`, `sample_signals`, `propose_fix`, `rerun_sim`. `max_steps` 기본 10 (F1, 2026-11-26: 형식 오류와 거부된 보고서는 단계로 세지 않고 케이스당 `max_free_turns`=3까지 허용. spi0·uart0·i2c0 기준선은 8단계, 형식 오류도 단계로 셈).
- 결과 카테고리: `exact / near / wrong_line / wrong_file / not_rtl_bug / no_report`.
- `rerun_sim`: 패치된 RTL 복사본 + 원본 사람 TB로 재시뮬레이션. 최대 3회, 제안별 캐시, **스텝을 소모**한다. `fix_proposal_ids`에는 rerun_sim이 PASS한 제안만 올리라는 프롬프트 규칙(rule 7)이 있다.
- `check_fix`: 사후 검증. 주석 제거 + 공백 압축 후 골든과 같은지 비교. 느슨한 규칙(주장한 제안 중 하나라도 통과하면 pass).

### TB 규약 (Agent가 로그를 파싱한다)
- `timescale` 지시문을 쓰지 않는다(xsim은 timescale이 있는 모듈과 없는 모듈이 섞이면 XSIM 43-4099 에러).
- 불일치는 `CHECK_FAIL t=.. sig=.. exp=.. got=..` 한 줄씩(최대 10개), 마지막에 `CHECKS total=.. mismatches=..` 와 `[TB] PASS` 또는 `[TB] FAIL: ...` 한 줄.
- 시간 초과 watchdog은 골든 종료 시간의 수 배 이내로 짧게 둔다(60ms로 뒀다가 xsim에서 TIMEOUT → invalid 처리된 사례가 있다).
- 변수는 사용 전에 선언한다(xsim은 선언 순서를 엄격히 본다).

### 변형 카탈로그 형식 (`bugs/<dut>/bugs.json`)
- 항목: `id, dut, type, file, find, replace, expect_count, description, equivalent`. 필요 시 `occurrence`.
- `type`은 `pointer/flag/reset/memory/guard/corner` 중 하나(`tests/test_bugs.py`가 sync_fifo 타입 집합 == `BUG_TYPES`를 단언하므로 임의로 늘리지 않는다).
- 동등 변형(`equivalent: true`)은 PASS가 정상(`equivalent_ok`). `TIMEOUT/COMPILE_ERROR/ELAB_ERROR`는 `invalid`로 분류되어 점수에서 빠진다.
- 새 DUT에서 `meta`에 `dut_top`을 지정하면 래퍼 top(예: `spi_system`)을 쓴다.

---

## 5. 측정된 결과 (sync_fifo 기준, 이전 세션)

- Agent 원인 위치 정확도 약 88%(sync_fifo).
- 수정안 검증 v0d: golden 12개 중 pass 1 / fail 2 / no_fix 2. v0e: pass 2 / fail 0 / no_fix 3. 실행 간 분산이 실제로 크다.
- 증거 도구(`get_log_snippet`, `read_tb`, `read_vcd_signal`, `sample_signals`) 사용: v0e 17건 중 0건. Agent가 RTL만 읽고 판단한다.
- 유령 수정(phantom fix) 사례: `count <= count;`. 클럭 로직 오해(비할당이 값을 유지하고, NBA는 에지 이전 값을 읽는다는 개념)에서 나온 것.
- B13은 `max_steps`(8)에 걸려 놓침. `rerun_sim`이 스텝을 소모하기 때문.

> 알려진 문제와 이후 대응 계획은 `CLAUDE.local.md`와 `docs/NOTES_ps7.md`/`NOTES_ps8.md`를 본다.

## 6. Phase 8 현황 (가장 중요)

### 8-1 SPI DUT
- `dut/spi/rtl/`: clock_divider, Master_FSM, Master, Master_RX, Master_TX, **Slave**, Slave_RX, Slave_TX, **spi_system**(단일 top 래퍼). 포트: ck, reset, start, master_tx_data, slave_tx_data, master_rx_data, slave_rx_data, spi_clk, CS, MOSI, MISO, busy, done.
- SPI mode 0, 8-bit, MSB first, 데이터 선로는 spi_clk 하강 에지에서만 바뀐다.
- 사용자의 원본 RTL에서 발견된 **골든 버그**: CS가 start에서 조합으로 나오고 TX는 negedge로 세는 구조라 start 위상 경쟁이 있다. 수정(fix2): `Master_FSM`에서 `start_q <= start && (state == IDLE)`를 spi_clk negedge에서 래치. 래치만 하는 fix1은 DONE 중 start나 start 유지에서 실패한다.
- `Slave.v`는 사용자가 올린 `SPI_Slave.v`가 낡은 복사본이라 **TB 포트를 보고 내가 새로 썼다.** 사용자의 실제 Slave와 다를 수 있다 → 확인 필요.
- TB `dut/spi/tb/tb_spi_sc.v`(top `spi_sc_tb`): 골든 4094 체크, 0 불일치. spi_clk 첫 에지는 리셋 해제 후 490ns, 주기 1000ns.
- 카탈로그: B01–B30 + 동등 E01, E02. 비동등 타입 수: pointer 8, guard 7, corner 6, reset 5, flag 4 (동등: corner 1, flag 1).
- **xsim 결과(2026-11-25)**: 골든 PASS. 29 detected, 1 invalid(B03: `spi_clk` 고정 → TB watchdog 60ms가 xsim 제한 시간을 넘김), 2 equivalent_ok. 이후 watchdog을 3ms로 줄였고(골든은 약 0.89ms에 종료) 재실행에서 B03 detected → **30/30, invalid 0** (`runs/dut_spi_eval_20261125_221408`).
- TB `check` 태스크의 이름 인자가 `[127:0]`(16자)이라 17자 이상 체크 이름이 앞에서 잘려 로그에 찍혔다(`usy_rise_timeout`, `change_at_rising` 등, 첫 실패 신호 기준 9/30건, B17/B28은 MOSI/MISO 구분 불가). Agent 입력 결함이라 spi0 전에 `[8*24-1:0]`로 고쳤다. 재실행에서 판정·시각은 그대로 30/30, 이름 정상 (`runs/dut_spi_eval_20261125_222936`, xsim).
- mutation score 100%는 **낙관적**이다. 변형도 TB도 같은 사람이 만들고 맞춰서(B17/B28/B30을 놓쳐서 체크를 추가함) 나온 값이라 TB 강도의 증거가 아니다. Agent 측정용 정답 세트로만 쓴다.

### 다음 단계 (순서 고정)
1. ~~`python -m scripts.run_eval --dut spi` 재실행 → B03 detected 확인~~ ✅ 완료 (TB 이름 폭 수정 포함)
2. `python -m scripts.llm_ping`
3. `python -m scripts.run_debug_eval --dut spi --dry-run` (기대: "DUT spi: 평가 대상 30개")
4. `python -m scripts.run_debug_eval --dut spi --no-cache --label spi0`
5. `python -m scripts.verify_fixes --dut spi --label spi0`
6. 결과를 아래 기준으로 해석하고, 그 다음에 `CLAUDE.local.md` §B의 문제들에 대응

### ⚠ 규칙: 첫 SPI 측정 전에는 Agent를 수정하지 않는다
sync_fifo에서 튜닝한 Agent를 **그대로** SPI에 돌려야 일반화 성능이 보인다. 아래 기준은 결과를 보기 전에 정한 것이다.
- 원인 위치 정확도가 sync_fifo(약 88%) 대비 어떤지
- 증거 도구를 쓴 케이스 수 (sync_fifo는 0/17)
- `max_steps`에 걸린 케이스 수
- 수정 카테고리 분포 (pass/fail/no_fix)
- 클럭 로직 오해 패턴(유령 주장)이 재현되는지
결과를 본 뒤에 기준을 바꾸지 말고, 바꿔야 하면 바꿨다고 기록한다.

### 이후 Phase 8 계획
- 8-2: UART, I2C로 같은 측정 반복. UART는 사용자 RTL(`Projects/UART_mid-bit`) 그대로. **I2C는 사용자 요청으로 Claude가 사용자 스타일에 맞춰 RTL을 작성**(사용자 I2C는 미완성이었음) → RTL·TB·변형 모두 Claude 작성이라 측정 편향이 가장 크다. 리포트에 명시
- 8-3: Regression Manager, Report Generator, `run_agent.py` + `run_agent.bat`
  - 목표 사용: `dut/` 폴더에 RTL과 spec(필요하면 TB)만 넣고 bat 실행 → 명령어 입력 없이 전 과정이 돌고 report 생성
  - 아이디어 후보(필수 아님): SVA 기반 판정 근거(SystemVerilog 단계), 커버리지 요약을 Agent 입력에 포함, 리포트 자동 생성

---

## 7. 포트폴리오/README 방향
- README는 취업용이다. "무엇을 설계했고 → 어떻게 구현/검증했고 → 어떤 문제를 해결했는가"가 드러나야 한다.
- 구성: Overview, Spec, Architecture, Block/FSM Diagram, Module Hierarchy, RTL, Testbench, Simulation, Waveform, Verification Result, Key Learning, Future Improvement.
- 정량 근거(mutation score, 위치 정확도, 수정 pass율)는 한계와 함께 쓴다. "AI가 만든 코드를 그대로 쓴다"를 AI 활용 역량으로 과대 포장하지 않는다. 사용자가 직접 분석하고 수정한 지점을 분명히 쓴다.
- async FIFO RTL에서 수동 분석으로 찾은 버그는 Agent 완성 전에는 수정하지 않고, 완성 후 수정하면서 실제 적용 사례로 문서화한다.

---

## 8. 테스트
- `pytest -q` 전체 611개가 기대값(F5+F2b 추가 후). `tests/test_spi_dut.py` 9개, `tests/test_uart_dut.py` 3개, `tests/test_i2c_dut.py` 3개(Icarus 필요).
- Icarus가 없는 환경에서는 일부 테스트가 건너뛰거나 실패할 수 있다. 실패하면 환경 문제인지 코드 문제인지 구분해서 보고한다.
- `sim` 패키지(`sim/runner.py`)가 없으면 `core/compile_gate.py` import가 실패한다. 프로젝트 루트에서 실행한다.
