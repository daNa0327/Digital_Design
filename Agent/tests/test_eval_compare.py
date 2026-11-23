"""6-4: TB 평가 결과 비교(core/eval_compare)와 run_eval의 --tb 인자 해석.

비교는 results.json 형식의 dict만 다루는 순수 함수라 시뮬레이터 없이 검증한다.
"""

from argparse import Namespace
from pathlib import Path

import pytest

from core.eval_compare import compare_reports, render_comparison_markdown
from scripts.run_eval import resolve_run


def row(bug_id, outcome, sig="full", t=10_000, typ="pointer"):
    """변형 한 건의 결과. detected면 첫 불일치 신호와 시각(ps)을 가진다."""
    det = outcome == "detected"
    return {"bug_id": bug_id, "type": typ, "equivalent": False, "outcome": outcome,
            "status": "FAIL" if det else "PASS", "tb_verdict": "FAIL" if det else "PASS", "line": 1,
            "first_fail_signal": sig if det else None, "first_fail_time_ps": t if det else None,
            "n_mismatches": 3 if det else 0, "total_checks": 100, "duration_s": 1.0, "workdir": ""}


def report(rows, golden="PASS", aborted=False):
    det = sum(r["outcome"] == "detected" for r in rows)
    sur = sum(r["outcome"] == "survived" for r in rows)
    return {"dut": "d", "golden": {"status": golden, "tb_verdict": golden}, "aborted": aborted, "results": rows,
            "summary": {"total": len(rows), "detected": det, "survived": sur, "invalid": 0, "equivalent_ok": 0,
                        "mutation_score": det / (det + sur) if det + sur else None}}


A = report([row("B1", "detected", t=5_000), row("B2", "detected", t=7_000), row("B3", "survived"),
            row("B4", "survived")])
B = report([row("B1", "detected", t=9_000), row("B2", "survived"), row("B3", "detected"),
            row("B4", "survived")])


# ------------------------------------------------------------ 비교 계산
def test_classifies_only_a_only_b_both_and_neither():
    """한쪽만 잡은 변형, 둘 다 잡은 변형, 둘 다 못 잡은 변형이 정확히 나뉜다."""
    c = compare_reports(A, B)
    assert c["only_a"] == ["B2"] and c["only_b"] == ["B3"]
    assert c["both_detected"] == ["B1"] and c["both_survived"] == ["B4"]


def test_rows_keep_catalog_order_and_both_outcomes():
    """변형별 행은 A의 순서를 따르고 양쪽 결과를 담는다."""
    c = compare_reports(A, B)
    assert [r["bug_id"] for r in c["rows"]] == ["B1", "B2", "B3", "B4"]
    assert (c["rows"][1]["a"], c["rows"][1]["b"]) == ("detected", "survived")


def test_summaries_are_carried_through():
    """각 쪽의 mutation score가 그대로 전달된다."""
    c = compare_reports(A, B)
    assert c["summary"]["a"]["mutation_score"] == 0.5 and c["summary"]["b"]["mutation_score"] == 0.5


def test_time_pairs_only_for_bugs_both_detected():
    """첫 불일치 시각 쌍은 둘 다 잡은 변형에서만 만든다."""
    assert compare_reports(A, B)["time_pairs"] == [("B1", 5_000, 9_000)]


def test_bug_only_in_one_report_is_listed_with_note():
    """한쪽에만 있는 변형도 행으로 남기고 비고를 단다."""
    b = report([row("B1", "detected"), row("B9", "detected")])
    c = compare_reports(report([row("B1", "detected")]), b)
    last = c["rows"][-1]
    assert last["bug_id"] == "B9" and last["a"] is None and "한쪽 결과 없음" in last["note"]


def test_detected_without_check_fail_is_flagged():
    """FAIL로 잡혔지만 CHECK_FAIL(검사 불일치)이 없으면 의심 목록에 넣는다 (예: 워치독 타임아웃)."""
    r = row("B1", "detected")
    r["first_fail_signal"], r["first_fail_time_ps"] = None, None
    c = compare_reports(report([row("B1", "detected")]), report([r]))
    assert c["b_detected_without_check"] == ["B1"] and c["a_detected_without_check"] == []
    assert "B: 불일치 없이 FAIL" in c["rows"][0]["note"]


def test_aborted_golden_skips_mutant_comparison():
    """골든이 중단된 쪽이 있으면 변형 비교는 비운다."""
    c = compare_reports(A, report([], golden="FAIL", aborted=True))
    assert c["rows"] == [] and c["aborted"] == {"a": False, "b": True}


# ------------------------------------------------------------ 렌더링
def test_markdown_has_sections_labels_and_scores():
    """리포트에 골든, 요약, 차이, 변형별, 주의 절과 라벨, 점수가 들어간다."""
    md = render_comparison_markdown(compare_reports(A, B), "human", "llm",
                                    {"path": "a.v", "top": "ta", "sha256": "abc"}, {"path": "b.v", "top": "tb", "sha256": "def"})
    for s in ("# TB 비교: human vs llm", "## 골든", "## 요약", "## 차이", "## 변형별", "## 해석 시 주의",
              "human만 잡음: B2", "llm만 잡음: B3", "둘 다 못 잡음: B4", "50.0%", "`a.v`", "sha256 `def`"):
        assert s in md


def test_markdown_for_aborted_golden_explains_false_failure():
    """골든이 FAIL하면 변형 표 대신 '거짓 실패' 설명만 낸다."""
    md = render_comparison_markdown(compare_reports(A, report([], golden="FAIL", aborted=True)), "human", "llm")
    assert "llm의 골든이 PASS가 아니라" in md and "거짓 실패" in md and "## 변형별" not in md


def test_markdown_warns_about_detection_without_check_fail():
    """검사 불일치 없는 검출은 리포트에서 경고로 보인다."""
    r = row("B1", "detected")
    r["first_fail_signal"], r["first_fail_time_ps"] = None, None
    md = render_comparison_markdown(compare_reports(report([row("B1", "detected")]), report([r])), "human", "llm")
    assert "⚠ llm: 검사 불일치(CHECK_FAIL) 없이 FAIL" in md


def test_markdown_reports_time_median_and_later_count():
    """둘 다 잡은 변형의 첫 불일치 시각 중앙값과 B가 더 늦은 개수를 보여준다."""
    md = render_comparison_markdown(compare_reports(A, B), "human", "llm")
    assert "human 5 ns, llm 9 ns" in md and "더 늦게 잡은 변형 1개" in md


# ------------------------------------------------------------ run_eval --tb 해석
META = {"dut": "sync_fifo", "golden_rtl": "dut/sync_fifo/rtl", "top": "sync_fifo_sc_tb"}


def args(**kw):
    base = dict(tb=None, tb_top=None, label=None, out=None)
    base.update(kw)
    return Namespace(**base)


def test_default_run_uses_human_tb_and_eval_prefix(tmp_path):
    """--tb가 없으면 기존과 같이 사람 TB, 카탈로그의 top, runs/eval_<시각>를 쓴다."""
    g, tb, top, out = resolve_run(args(), META, tmp_path)
    assert tb.name == "tb_sync_fifo_sc.v" and top == "sync_fifo_sc_tb"
    assert out.parent == tmp_path / "runs" and out.name.startswith("eval_")


def test_custom_tb_reads_top_from_code_and_uses_tbeval_prefix(tmp_path):
    """--tb를 주면 top을 코드에서 읽고, 결과는 기준선 리포트와 섞이지 않게 tbeval_<label>_로 저장된다."""
    f = tmp_path / "x.v"
    f.write_text("// c\nmodule tb_llm;\nendmodule\n")
    _, tb, top, out = resolve_run(args(tb=str(f), label="llm"), META, tmp_path)
    assert tb == f and top == "tb_llm" and out.name.startswith("tbeval_llm_")
    assert not out.name.startswith("eval_")


def test_tb_top_override_and_label_default(tmp_path):
    """--tb-top이 우선하고, 라벨이 없으면 파일 이름을 쓴다."""
    f = tmp_path / "my_tb.v"
    f.write_text("module a;\nendmodule\n")
    _, _, top, out = resolve_run(args(tb=str(f), tb_top="forced"), META, tmp_path)
    assert top == "forced" and out.name.startswith("tbeval_my_tb_")


def test_missing_tb_file_exits(tmp_path):
    """없는 TB 파일은 종료 메시지와 함께 거부한다."""
    with pytest.raises(SystemExit, match="TB 파일이 없습니다"):
        resolve_run(args(tb=str(tmp_path / "nope.v")), META, tmp_path)


def test_tb_without_module_exits(tmp_path):
    """module을 못 찾는 파일은 --tb-top을 요구하며 거부한다."""
    f = tmp_path / "e.v"
    f.write_text("// nothing\n")
    with pytest.raises(SystemExit, match="--tb-top"):
        resolve_run(args(tb=str(f)), META, tmp_path)


def test_explicit_out_overrides_default_folder(tmp_path):
    """--out을 주면 그 폴더를 그대로 쓴다."""
    f = tmp_path / "t.v"
    f.write_text("module t;\nendmodule\n")
    _, _, _, out = resolve_run(args(tb=str(f), out=str(tmp_path / "o")), META, tmp_path)
    assert out == Path(tmp_path / "o")