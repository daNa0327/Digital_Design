"""평가 결과(results.json)를 사람이 읽는 Markdown 리포트로 만든다 (순수 함수, 시뮬레이터 불필요)."""

from __future__ import annotations

from statistics import median

_OUTCOME_LABEL = {
    "detected": "detected",
    "survived": "**survived**",
    "invalid": "**invalid**",
    "equivalent_ok": "equivalent (정상 생존)",
    "equivalent_unexpected_detect": "**equivalent인데 잡힘**",
}


def _ns(ps) -> str:
    if ps is None:
        return "-"
    ns = ps / 1000
    return f"{ns:g} ns"


def render_baseline_markdown(report: dict, title: str = "Baseline: TB-only 평가") -> str:
    """report는 EvalReport.to_dict() 또는 results.json을 읽은 dict."""
    g, s, rows = report["golden"], report["summary"], report["results"]
    L: list[str] = [f"# {title}: {report['dut']}", ""]
    L += ["LLM/Agent 없이 결정적 구간(`XsimSim` → `analyze`)과 self-checking TB만으로 "
          "정답을 아는 버그를 얼마나 잡는지 잰 기준선이다. 이후 Agent의 성능은 이 기준선과 비교한다.", ""]

    L += ["## 골든", "", f"- status: `{g['status']}`, tb_verdict: `{g['tb_verdict']}`"]
    if report["aborted"]:
        L += ["", "**골든이 PASS가 아니라 평가를 중단했다. 변형 결과는 없다.**", ""]
        return "\n".join(L) + "\n"
    L += [""]

    score = "n/a" if s["mutation_score"] is None else f"{s['mutation_score']:.1%}"
    scored = s["detected"] + s["survived"]
    L += ["## 요약", "",
          "| 항목 | 값 |", "|---|---|",
          f"| 변형 수 (전체) | {s['total']} |",
          f"| 점수 대상 (동등/invalid 제외) | {scored} |",
          f"| detected | {s['detected']} |",
          f"| survived (TB가 못 잡음) | {s['survived']} |",
          f"| invalid (빌드 실패/타임아웃) | {s['invalid']} |",
          f"| 동등 변형 (정상 생존) | {s['equivalent_ok']} |",
          f"| 동등 변형이 잡힘 (메타데이터 오류) | {s['equivalent_unexpected_detect']} |",
          f"| **mutation score** | **{score}** |", ""]

    L += ["## 유형별", "", "| 유형 | detected | survived |", "|---|---|---|"]
    for t, v in s["by_type"].items():
        L.append(f"| {t} | {v['detected']} | {v['survived']} |")
    L.append("")

    times = [r["first_fail_time_ps"] for r in rows if r["outcome"] == "detected"
             and r["first_fail_time_ps"] is not None]
    if times:
        L += ["## 탐지 시점", "",
              f"첫 불일치 시각: 최소 {_ns(min(times))}, 중앙값 {_ns(median(times))}, 최대 {_ns(max(times))} "
              f"(대상 {len(times)}개). 늦게 잡히는 변형일수록 특정 상황을 만들어야 드러나는 버그다.", ""]

    L += ["## 변형별 결과", "",
          "| id | 유형 | 패치 줄 | 결과 | 첫 불일치 | 불일치 수 | 실행 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        ff = f"`{r['first_fail_signal']}` @ {_ns(r['first_fail_time_ps'])}" if r["first_fail_signal"] else "-"
        mm = "-" if r["n_mismatches"] is None else f"{r['n_mismatches']}/{r['total_checks']}"
        L.append(f"| {r['bug_id']} | {r['type']} | {r['line']} | {_OUTCOME_LABEL.get(r['outcome'], r['outcome'])} "
                 f"| {ff} | {mm} | {r['duration_s']:.1f}s |")
    L.append("")

    if s["survivors"]:
        L += ["## 생존 변형 (TB 보강 후보)", ""] + [f"- {i}" for i in s["survivors"]] + [""]
    if s["problems"]:
        L += ["## 점검 필요", ""] + [f"- {i}" for i in s["problems"]] + [""]

    L += ["## 해석 시 주의", "",
          "- 점수 100%는 \"이 변형 세트를 TB가 모두 잡는다\"는 뜻이지 TB가 완전하다는 뜻이 아니다. 변형은 한 줄 치환 단일 버그뿐이다.",
          "- 동등 변형은 코드상 도달 불가능한 분기를 바꾼 것으로, 코드 읽기와 두 시뮬레이터에서의 PASS로 판단했으며 형식 검증을 한 것은 아니다.",
          "- 랜덤 구간은 고정 seed라 결정적이다. 늦게 잡히는 변형은 seed나 길이를 바꾸면 결과가 달라질 수 있다.", ""]
    return "\n".join(L)