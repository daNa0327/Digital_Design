# Phase 3 NOTES: VCD Reader와 Agent용 VCD 도구

> RTL Verification AI Agent 개발의 Phase 3 기록.
> 목적: 시뮬레이션이 남긴 `dump.vcd`를 **시뮬레이터 무관하게 읽고**, Debug Agent(LLM)가 안전하게 조회할 수 있는 도구로 감싼다.
> LLM은 쓰지 않는다. 파싱, 조회, 길이 제한은 모두 결정적 계층이다.
> 작성 기준일: 2026-11-20 / 대상 DUT: async FIFO

상태 표기: ✅ 확인됨 · ⚠️ 부분 확인/추정 · ❓ 미확인(가설) · ⏸ 보류

---

## 1. 구조

```
dump.vcd ──▶ VcdReader ──▶ VcdTools ──▶ (Phase 7) Debug Agent
            (파싱, 조회)   (상한, 오류 dict, 스키마)
```

| 파일 | 역할 |
|---|---|
| `core/vcd_reader.py` | `VcdReader`, `VcdSignal`: 파싱, 값 조회, 에지 샘플링, net 후보, 상태 점검 |
| `core/vcd_tools.py` | `VcdTools`, `TOOL_SPECS`, `dispatch`: LLM에 노출할 도구 3개 |
| `tests/test_vcd_reader.py` | 21개 (실제 샘플 기반 2개 포함) |
| `tests/test_vcd_tools.py` | 10개 |

## 2. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 저장 단위 | 이력을 **ID 기준**으로 저장, 이름→ID는 별도 | 같은 ID를 여러 계층 이름이 공유함 (Phase 0 실측). 이름 기준이면 덮어써짐 |
| `value_at(t)` | t 이하의 마지막 변화값, 첫 변화 이전은 `None` | VCD는 값이 바뀔 때만 기록 |
| `end_time_ps` | 마지막 타임스탬프 | 시뮬 종료 시각이 아님 (종료 시각은 로그의 `$finish`: 402ns, VCD는 400ns) |
| 시각 단위 | 모두 ps 정수 | 로그 쪽 `finish_time_ps`와 통일 |
| 벡터 | 폭에 맞춰 확장 (`b101` → `00000101`, `bx` → `xxxxxxxx`) | VCD는 앞쪽 비트를 생략할 수 있음 |
| 잘린 파일 | 줄바꿈 없이 끝난 마지막 줄은 버림 | 타임아웃으로 죽인 xsim의 VCD 대비 |
| 파싱 방식 | 줄 단위 스트리밍 | 처음엔 파일 전체를 토큰 리스트로 만들었으나 큰 VCD에서 메모리 부담 |
| 적재 필터 | `from_file(signals=, until_ps=)` | 필요한 신호와 구간만 메모리에 올림. 적재하지 않은 신호 조회는 `ValueError` (조용히 빈 값을 주지 않음) |
| 에지 정의 | Verilog 규칙: 상승 `0→1`, `x→1`(그리고 `0→x/z`), 하강 `1→0`, `x→0` | `x→0`도 `negedge` |
| 샘플링 시점 | 기본 **에지 직전** 값 (`when="before"`) | 에지와 같은 시각에 바뀐 입력은 DUT가 이전 값을 읽음 |
| net 후보 | `alias`(같은 ID, 확실)와 `same_history`(ID 다름, 이력 같음, **후보**)를 분리 | 같은 이력이어도 같은 net이라는 증명은 아님 |
| 후보 제한 | 기록 2건 미만(상수)은 제외, 마지막 이름이 같은 신호끼리만 비교 | 상수 신호의 우연한 일치를 막음 |
| 상태 점검 | `status()`: `not_in_vcd`, `not_loaded`, `no_changes`, `always_x`, `ok` | Agent가 근거 없는 결론을 내리지 않게 |
| 도구 오류 | 예외 대신 `{"error": ...}` + 이름 제안, `dispatch()`가 모두 흡수 | Agent 루프가 도구 오류로 죽지 않게 |
| 출력 상한 | 목록 100 / 변화 200 / 행 100 / 샘플 신호 10, 초과 시 `truncated`와 `next_t0_ps` | LLM 컨텍스트 보호, 이어 읽기 지원 |

## 3. 측정 결과

### 3.1 실제 async FIFO VCD ✅

| 항목 | 결과 |
|---|---|
| 타임스케일, 마지막 타임스탬프 | `1ps`, `#400000` (테스트로 확인) |
| 신호 이름 | 계층 이름 그대로 읽힘 (`async_fifo_tb.dut.c1.wr_ck` 등) |
| `wr_ck` 상승 에지 | **40개**, 첫 에지 5ns, 주기 10ns |
| `tb.wr_ck`와 `dut.wr_ck` | **ID가 다르다.** `dut`, `c1`, `m1`의 `wr_ck`는 서로 같은 ID(alias)이고, `tb.wr_ck`는 별도 ID지만 이력이 같아 `same_history` 후보로 잡힘 |
| `mem` 배열 | VCD에 없음 (`status` = `not_in_vcd`) |

`read_vcd_signal("async_fifo_tb.wr_ck", 0, 50000)` 실제 응답: 변화 11건, `aliases: []`, `same_history_candidates: [dut.wr_ck, c1.wr_ck, m1.wr_ck]`.

- 이 후보 3개는 서로 이미 alias인데 목록에는 따로 나온다. 중복이므로 후보를 ID 그룹으로 묶으면 응답이 더 짧아진다 (개선 후보, ⏸).
- 클럭처럼 자주 바뀌는 신호는 `changes` 목록이 길어진다. 클럭 자체보다 `sample_signals`로 에지 기준 값을 보는 쪽이 토큰 효율이 좋다.

### 3.2 타임아웃으로 죽인 xsim의 VCD ⚠️

`$finish`가 없는 TB를 10초 타임아웃으로 죽인 4회 실행:

| 항목 | 결과 |
|---|---|
| `dump.vcd` 크기 | 2.4MB / 20MB / 45MB / 94MB (실행마다 다름) |
| 마지막 줄 | 온전한 값 줄 (`0!`, `0"`, `0*`, `0+`) |
| 마지막 타임스탬프 | `#197750000` (197.75µs), 시뮬 종료 시각과 무관 |

- 읽을 수 있는 불완전한 파일이 남는다. 끊기는 지점은 **비결정적**이다 (클럭이 계속 돌아 10초 동안 쓰인 만큼이 남음).
- 줄 중간에서 잘렸을 가능성은 이번 파일에서는 보이지 않았지만 보장은 없다. 그래서 줄바꿈 없는 마지막 줄을 버린다.
- 따라서 TIMEOUT 상태의 VCD는 `end_time_ps`를 종료 시각으로 쓰지 말고, 증거로 쓸 때도 끊긴 파일임을 전제로 한다.
- 샘플 수집을 반복하면 `runs/`에 큰 hang 폴더가 쌓인다 (4개, 약 160MB). 지워도 된다.

### 3.3 큰 VCD 파싱 부하 ⚠️

합성 데이터(143MB, 변화 1,200만 건): **약 8.5초, 메모리 약 1.1GB.** 변화 이력을 파이썬 객체로 들고 있기 때문이다. 실제 hang VCD 94MB로는 직접 재지 않았다.

- 대응: 스트리밍 파싱(전체 텍스트를 올리지 않음), `signals=`/`until_ps=` 적재 필터.
- 한계: 이력 자체의 메모리는 신호 수와 변화 수에 비례한다. 큰 파일은 필요한 신호만 적재해야 한다.

## 4. 에지와 샘플링의 의미

```
에지 시각 t에서 TB가 입력 d를 바꾼 경우
  before (기본): d의 t 직전 값  → DUT 플립플롭이 실제로 읽은 값
  after        : d의 t 직후 값  → 에지에서 갱신된 결과
```

- 에지와 같은 시각에 바뀐 신호를 `after`로 보면 "DUT가 새 값을 읽었다"고 잘못 해석한다. 그래서 기본은 `before`다.
- async FIFO는 도메인이 둘이다 (`wr_ck`, `rd_ck`). 신호는 자기 도메인 클럭으로 샘플링해야 한다. `tb`에서 `wr_ck`와 `rd_ck`는 서로 다른 시각에 에지가 있다.

## 5. Agent용 도구

| 도구 | 입력 | 출력 핵심 |
|---|---|---|
| `list_signals` | `pattern`, `limit` | 이름, 폭, alias 수, `truncated` |
| `read_vcd_signal` | `name`, `t0_ps`, `t1_ps`, `max_changes`, `fmt` | 구간 변화(시작 값 포함), `status`, `aliases`, `same_history_candidates`, `next_t0_ps` |
| `sample_signals` | `clock`, `signals`, `t0_ps`, `t1_ps`, `max_rows`, `when`, `edge`, `fmt` | 에지별 값 표, `total_edges`, `next_t0_ps` |

- `read_vcd_signal` 도구 설명에 "값이 x이거나 status가 ok가 아니면 alias와 교차 확인 전에 결론내지 말 것"을 넣었다.
- `fmt`는 `bin`/`hex`/`dec`. 벡터에 x가 섞이면 이진 문자열을 그대로 반환한다.
- `TOOL_SPECS`는 JSON 스키마라서 Phase 7에서 API의 `tools=`에 바로 넘길 수 있다. 실제 LLM 호출로는 아직 검증하지 않았다 (❓).

## 6. 검증 결과

자동 테스트 **78 passed** ✅ (이전 47 + 31)

| 파일 | 개수 | 내용 |
|---|---|---|
| `test_vcd_reader.py` | 21 | 헤더/타임스케일, alias, `value_at`, 벡터 확장, `window`, 잘린 파일, 에지 규칙, 샘플 직전/직후, 적재 필터, `until_ps`, net 후보, 상태 코드, 실제 샘플 2개 |
| `test_vcd_tools.py` | 10 | 목록 필터와 잘림, alias/후보 동반, 이어 읽기, 하드 상한, 오류와 이름 제안, 값 표기, 샘플 표, `dispatch` 오류 흡수, 스키마, 실제 샘플 1개 |

실제 샘플 기반 테스트는 총 3개이고 샘플 VCD가 없으면 건너뛴다.

## 7. 한계 및 미확인

| 항목 | 상태 | 비고 |
|---|---|---|
| `mem` 같은 unpacked array | ✅ 확인 | VCD에 없음. 포인터와 출력 신호(`data_out`)로 추론해야 함 |
| 줄 중간에서 잘린 VCD | ❓ | 만나지 못했고 규칙으로만 대비함 |
| `$timescale` 단위 `fs` | ⏸ | 미지원 (`ValueError`) |
| `real` 값, 다중 `$scope` 종류 | ⏸ | `real` 값은 문자열로 저장만 하고 별도 처리 없음 |
| 94MB hang VCD 실제 파싱 시간 | ❓ | 합성 데이터만 측정함 |
| `same_history`의 오탐 | ⚠️ | 이력이 같아도 같은 net이 아닐 수 있음 (후보로만 사용) |
| 후보 목록의 중복(서로 alias) | ⏸ | ID 그룹으로 묶으면 응답이 짧아짐 |
| LLM이 도구를 실제로 올바르게 쓰는지 | ❓ | Phase 7에서 검증 |
| 시뮬레이터 로그와 VCD의 결합 | ⏸ | 에러 시각(`time_ps`)으로 VCD 구간을 조회하는 흐름은 Phase 7에서 |

Phase 0~2에서 이어진 항목 (async FIFO `empty` 비대칭, 골든 DUT 문제, 기준 TB가 self-checking이 아님)은 그대로 보류다.

## 8. 작업 중 얻은 교훈

- **큰 파일은 처음부터 스트리밍으로.** 전체를 토큰으로 쪼개는 방식은 동작은 하지만 94MB급에서 부담이 된다.
- **테스트 데이터도 형식을 지킨다.** VCD 스칼라는 `x`와 ID를 붙여 쓴다(`xx`). 띄어 쓴 합성 데이터로 테스트가 틀려서 구현을 의심할 뻔했다.
- **내가 세운 가정이 틀릴 수 있다.** `x→0`을 에지가 아니라고 가정한 테스트가 틀렸고, Verilog 규칙(`negedge`)이 맞았다.
- **"후보"와 "사실"을 이름으로 구분한다.** `alias`(확실)와 `same_history_candidates`(후보)를 필드 이름부터 나눠서 Agent가 둘을 같은 확신으로 쓰지 못하게 했다.
- **도구는 실패해도 루프를 죽이면 안 된다.** 오류를 dict로 돌려주면 LLM이 이름을 고쳐서 다시 시도할 수 있다.

## 9. 다음 단계 (Phase 4: 버그 주입 세트와 평가 하네스)

| 확인된 사실 | 설계 |
|---|---|
| 기준 TB는 self-checking이 아님 | 평가용 TB에 `[TB] PASS/FAIL` 규약 필요 |
| async FIFO의 `empty` 비대칭은 Agent 완성 후 수정하기로 함 | 골든 DUT는 다른 DUT 또는 수정본으로 |
| 에러 시각은 `ErrorItem.time_ps`, 파형은 `VcdTools`로 조회 | 정답 메타데이터(버그 위치, 유형, 첫 이상 시각)와 맞춰 볼 수 있어야 함 |

| # | 내용 |
|---|---|
| 4-1 | 골든 DUT 선정과 self-checking TB 확보 |
| 4-2 | 버그 주입 방식(수동 변형본)과 정답 메타데이터 형식 |
| 4-3 | 평가 하네스: 골든/버그본 일괄 실행, `SimResult` 수집 |
| 4-4 | 베이스라인 지표(결정적 구간만): 탐지율 등 |

## 10. 명령어 요약

```powershell
cd C:\Users\Junyoung\Desktop\Verilog\Agent
.\.venv\Scripts\Activate.ps1

pytest -q                                  # 78 passed (Vivado 통합 포함 약 30초)

# 실제 VCD로 도구 응답 확인
python -c "import json; from core.vcd_reader import VcdReader as V; from core.vcd_tools import VcdTools as T; t=T(V.from_file('tests/data/ok_async_fifo.vcd')); print(json.dumps(t.read_vcd_signal('async_fifo_tb.wr_ck',0,50000)))"

# 에지 수
python -c "from core.vcd_reader import VcdReader as V; r=V.from_file('tests/data/ok_async_fifo.vcd'); print(len(r.edges('async_fifo_tb.wr_ck')))"
```