"""평가 리포트 렌더링 테스트 (순수 함수)."""

from core.eval_report import render_baseline_markdown
from core.evaluator import BugResult, summarize


def _report(results, aborted=False, golden="PASS"):
    return {"dut": "sync_fifo", "aborted": aborted,
            "golden": {"status": golden, "tb_verdict": golden},
            "summary": summarize(results), "results": [r.__dict__ for r in results]}


def _r(i, t, outcome, sig=None, t_ps=None, eq=False):
    return BugResult(i, t, eq, outcome, "FAIL" if outcome == "detected" else "PASS", None, 10,
                     sig, t_ps, 5 if sig else 0, 100, 10.0, "w")


def test_render_summary_table_score_and_detection_times():
    """요약 표, mutation score, 유형별 표, 탐지 시점(최소/중앙값/최대, ns)이 들어간다."""
    md = render_baseline_markdown(_report([
        _r("B01", "pointer", "detected", "data_out", 167_000),
        _r("B02", "flag", "detected", "full", 97_000),
        _r("B03", "guard", "survived"),
        _r("E01", "pointer", "equivalent_ok", eq=True)]))
    assert "| **mutation score** | **66.7%** |" in md
    assert "| pointer | 1 | 0 |" in md and "| guard | 0 | 1 |" in md
    assert "최소 97 ns, 중앙값 132 ns, 최대 167 ns" in md
    assert "`data_out` @ 167 ns" in md and "equivalent (정상 생존)" in md
    assert "## 생존 변형" in md and "- B03" in md


def test_render_handles_aborted_and_empty_cases():
    """골든 실패 시 중단 안내만 나오고, 점수 대상이 없으면 n/a로 표시한다."""
    md = render_baseline_markdown(_report([], aborted=True, golden="FAIL"))
    assert "골든이 PASS가 아니라 평가를 중단했다" in md and "변형별 결과" not in md
    md2 = render_baseline_markdown(_report([_r("E01", "pointer", "equivalent_ok", eq=True)]))
    assert "| **mutation score** | **n/a** |" in md2 and "## 생존 변형" not in md2