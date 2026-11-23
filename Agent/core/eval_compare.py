"""6-4: 두 TB(예: 사람이 쓴 TB와 LLM이 만든 TB)의 평가 결과를 같은 변형 세트 위에서 비교한다.

입력은 평가 하네스가 만든 results.json(EvalReport.to_dict()) 두 개이고, 순수 함수라 시뮬레이터가 필요 없다.
비교의 초점은 점수 하나가 아니라 "어떤 변형을 한쪽만 잡는가"와 "정말 검사 불일치로 잡았는가"이다.

공개 API:
    compare_reports(a, b) -> dict
    render_comparison_markdown(cmp, label_a, label_b, tb_a=None, tb_b=None) -> str
"""

from __future__ import annotations

from statistics import median


def _ns(ps) -> str:
    return "-" if ps is None else f"{ps / 1000:g} ns"


def _row_map(report: dict) -> dict:
    return {r["bug_id"]: r for r in report["results"]}


def _ff(r: dict | None) -> str:
    if not r or not r.get("first_fail_signal"):
        return "-"
    return f"`{r['first_fail_signal']}` @ {_ns(r['first_fail_time_ps'])}"


def compare_reports(a: dict, b: dict) -> dict:
    """a, b의 골든/요약/변형별 결과를 맞대어 차이를 계산한다. 골든이 중단된 쪽이 있으면 변형 비교는 비운다."""
    out = {"golden": {"a": a["golden"], "b": b["golden"]}, "aborted": {"a": a["aborted"], "b": b["aborted"]},
           "summary": {"a": a["summary"], "b": b["summary"]}, "rows": [], "only_a": [], "only_b": [],
           "both_detected": [], "both_survived": [], "b_detected_without_check": [], "a_detected_without_check": [],
           "time_pairs": []}
    if a["aborted"] or b["aborted"]:
        return out

    ra, rb = _row_map(a), _row_map(b)
    ids = list(ra) + [i for i in rb if i not in ra]
    for i in ids:
        x, y = ra.get(i), rb.get(i)
        ox, oy = (x or {}).get("outcome"), (y or {}).get("outcome")
        note = []
        if ox == "detected" and oy == "survived":
            out["only_a"].append(i)
        elif ox == "survived" and oy == "detected":
            out["only_b"].append(i)
        elif ox == oy == "detected":
            out["both_detected"].append(i)
            if x["first_fail_time_ps"] is not None and y["first_fail_time_ps"] is not None:
                out["time_pairs"].append((i, x["first_fail_time_ps"], y["first_fail_time_ps"]))
        elif ox == oy == "survived":
            out["both_survived"].append(i)
        # 'detected'인데 CHECK_FAIL이 없다 = 검사 불일치가 아니라 타임아웃 등 다른 이유로 FAIL
        if oy == "detected" and not y["first_fail_signal"]:
            out["b_detected_without_check"].append(i)
            note.append("B: 불일치 없이 FAIL")
        if ox == "detected" and not x["first_fail_signal"]:
            out["a_detected_without_check"].append(i)
            note.append("A: 불일치 없이 FAIL")
        if x is None or y is None:
            note.append("한쪽 결과 없음")
        out["rows"].append({"bug_id": i, "type": (x or y)["type"], "a": ox, "b": oy,
                            "a_ff": _ff(x), "b_ff": _ff(y), "note": ", ".join(note)})
    return out


def _score(s: dict) -> str:
    return "n/a" if s["mutation_score"] is None else f"{s['mutation_score']:.1%}"


def render_comparison_markdown(cmp: dict, label_a: str, label_b: str, tb_a: dict | None = None,
                               tb_b: dict | None = None, title: str = "TB 비교") -> str:
    L: list[str] = [f"# {title}: {label_a} vs {label_b}", ""]
    for lab, tb in ((label_a, tb_a), (label_b, tb_b)):
        if tb:
            L.append(f"- **{lab}**: `{tb.get('path')}` (top `{tb.get('top')}`, sha256 `{tb.get('sha256')}`)")
    L.append("")

    ga, gb = cmp["golden"]["a"], cmp["golden"]["b"]
    L += ["## 골든 (정상 RTL에서 PASS해야 함)", "", "| TB | status | tb_verdict |", "|---|---|---|",
          f"| {label_a} | `{ga['status']}` | `{ga['tb_verdict']}` |", f"| {label_b} | `{gb['status']}` | `{gb['tb_verdict']}` |", ""]
    if cmp["aborted"]["a"] or cmp["aborted"]["b"]:
        who = [lab for lab, k in ((label_a, "a"), (label_b, "b")) if cmp["aborted"][k]]
        L += [f"**{', '.join(who)}의 골든이 PASS가 아니라 평가가 중단되어 변형 비교를 할 수 없다.** "
              "정상 RTL에서 FAIL하는 TB는 검증 TB로 쓸 수 없다 (거짓 실패).", ""]
        return "\n".join(L) + "\n"

    sa, sb = cmp["summary"]["a"], cmp["summary"]["b"]
    scored = lambda s: s["detected"] + s["survived"]   # noqa: E731
    L += ["## 요약", "", f"| 항목 | {label_a} | {label_b} |", "|---|---|---|",
          f"| 점수 대상 변형 | {scored(sa)} | {scored(sb)} |", f"| detected | {sa['detected']} | {sb['detected']} |",
          f"| survived | {sa['survived']} | {sb['survived']} |", f"| invalid | {sa['invalid']} | {sb['invalid']} |",
          f"| **mutation score** | **{_score(sa)}** | **{_score(sb)}** |", ""]

    L += ["## 차이", "",
          f"- {label_a}만 잡음: {', '.join(cmp['only_a']) or '없음'}",
          f"- {label_b}만 잡음: {', '.join(cmp['only_b']) or '없음'}",
          f"- 둘 다 못 잡음: {', '.join(cmp['both_survived']) or '없음'}",
          f"- 둘 다 잡음: {len(cmp['both_detected'])}개", ""]
    if cmp["time_pairs"]:
        ta = [p[1] for p in cmp["time_pairs"]]
        tb = [p[2] for p in cmp["time_pairs"]]
        later = sum(1 for _, x, y in cmp["time_pairs"] if y > x)
        L += [f"- 둘 다 잡은 {len(cmp['time_pairs'])}개의 첫 불일치 시각 중앙값: {label_a} {_ns(median(ta))}, "
              f"{label_b} {_ns(median(tb))} ({label_b}가 더 늦게 잡은 변형 {later}개). "
              "시각은 TB마다 시나리오 순서가 달라 단순 비교는 어렵다.", ""]
    for lab, key in ((label_a, "a_detected_without_check"), (label_b, "b_detected_without_check")):
        if cmp[key]:
            L += [f"- ⚠ {lab}: 검사 불일치(CHECK_FAIL) 없이 FAIL로 잡힌 변형 {', '.join(cmp[key])} - "
                  "타임아웃 등 다른 이유일 수 있어 실제 검출로 인정할지 확인 필요", ""]

    L += ["## 변형별", "", f"| id | 유형 | {label_a} | {label_b} | {label_a} 첫 불일치 | {label_b} 첫 불일치 | 비고 |",
          "|---|---|---|---|---|---|---|"]
    for r in cmp["rows"]:
        L.append(f"| {r['bug_id']} | {r['type']} | {r['a']} | {r['b']} | {r['a_ff']} | {r['b_ff']} | {r['note']} |")
    L += ["", "## 해석 시 주의", "",
          "- 변형 세트는 한 줄 치환 단일 버그 19개다. 점수가 같아도 TB가 같은 품질이라는 뜻은 아니다.",
          "- LLM TB는 RTL 소스를 보고 만들었다. 변형 세트(버그 목록)는 보여주지 않았지만, 참조 모델이 RTL 구조를 따랐을 수 있다.",
          "- LLM 출력은 비결정적이다. 이 비교는 한 번의 생성 결과이며(온도 0, 캐시됨), 다른 생성에서는 점수가 달라질 수 있다.",
          "- 골든 PASS는 필수 조건이다. 정상 RTL에서 FAIL하는 TB는 점수와 무관하게 쓸 수 없다.", ""]
    return "\n".join(L)