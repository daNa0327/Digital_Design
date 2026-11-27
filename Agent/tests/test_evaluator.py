"""평가 하네스 테스트 (Vivado 불필요: 가짜 Runner로 판정 규칙과 집계를 검증한다)."""

import json
from pathlib import Path

import pytest

from core.bugs import load_catalog
from core.evaluator import (BugResult, Judged, classify, evaluate, parse_check_fails,
                            parse_checks, summarize)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "bugs" / "sync_fifo" / "bugs.json"
GOLDEN = ROOT / "dut" / "sync_fifo" / "rtl"
TB = ROOT / "dut" / "sync_fifo" / "tb" / "tb_sync_fifo_sc.v"
TOP = "sync_fifo_sc_tb"


@pytest.fixture(scope="module")
def bugs():
    return load_catalog(CATALOG)


def _j(status, verdict=None, out="", wd=""):
    return Judged(status, verdict, out, 1.0, wd)


def test_parse_check_fails_units_and_noise():
    """CHECK_FAIL 줄만 읽고, 시각은 단위(ns/ps)에 맞춰 ps로 바꾼다. 단위가 없으면 None."""
    out = ("COVER full=1\nCHECK_FAIL t=97 ns sig=full exp=0 got=1 (model_count=7 wr_en=1 rd_en=0)\n"
           "CHECK_FAIL t=1500 ps sig=data_out exp=bb got=cc (model_count=2)\n"
           "CHECK_FAIL t=77 sig=empty exp=1 got=x (model_count=0)\nnoise CHECK_FAIL t=1 ns sig=a exp=0 got=1\n")
    fails = parse_check_fails(out)
    assert [(f.t_ps, f.signal, f.expected, f.got) for f in fails] == [
        (97_000, "full", "0", "1"), (1_500, "data_out", "bb", "cc"), (None, "empty", "1", "x")]
    assert [f.detail for f in fails] == ["(model_count=7 wr_en=1 rd_en=0)", "(model_count=2)", "(model_count=0)"]
    assert parse_checks("CHECKS total=4099 mismatches=12\n") == (4099, 12)
    assert parse_checks("nothing") == (None, None)


def test_classify_rules(bugs):
    """일반 변형: FAIL=detected, PASS/NO_VERDICT=survived. 빌드 실패/타임아웃=invalid. 동등 변형은 반대."""
    normal = next(b for b in bugs if not b.equivalent)
    equiv = next(b for b in bugs if b.equivalent)
    assert classify(normal, "FAIL") == "detected"
    assert classify(normal, "PASS") == "survived" and classify(normal, "NO_VERDICT") == "survived"
    for s in ("COMPILE_ERROR", "ELAB_ERROR", "TIMEOUT"):
        assert classify(normal, s) == "invalid" == classify(equiv, s)
    assert classify(equiv, "PASS") == "equivalent_ok"
    assert classify(equiv, "FAIL") == "equivalent_unexpected_detect"


def test_evaluate_runs_golden_first_and_classifies(bugs, tmp_path):
    """골든 PASS 후 변형을 실행하고, 변형마다 정답 메타데이터(줄 번호)와 첫 불일치를 기록한다."""
    calls = []

    def runner(files, top, workdir):
        calls.append(Path(workdir).parent.name if Path(workdir).name == "run" else Path(workdir).name)
        name = calls[-1]
        if name == "golden":
            return _j("PASS", "PASS", wd=workdir)
        b = next(x for x in bugs if x.id == name)
        if b.equivalent:
            return _j("PASS", "PASS", wd=workdir)
        if name.startswith("B16"):
            return _j("PASS", "PASS", wd=workdir)                       # 못 잡은 것으로 가정
        if name.startswith("B17"):
            return _j("COMPILE_ERROR", None, wd=workdir)                # 변형이 깨진 것으로 가정
        out = "CHECK_FAIL t=97 ns sig=full exp=0 got=1 (x)\nCHECKS total=100 mismatches=5\n[TB] FAIL: 5"
        return _j("FAIL", "FAIL", out, workdir)

    rep = evaluate(bugs, GOLDEN, TB, TOP, runner, tmp_path, dut="sync_fifo")
    assert calls[0] == "golden" and len(calls) == 1 + len(bugs)
    by = {r.bug_id: r for r in rep.results}
    assert by["B01_read_ptr_no_inc"].outcome == "detected"
    assert by["B01_read_ptr_no_inc"].first_fail_signal == "full"
    assert by["B01_read_ptr_no_inc"].first_fail_time_ps == 97_000
    assert (by["B01_read_ptr_no_inc"].n_mismatches, by["B01_read_ptr_no_inc"].total_checks) == (5, 100)
    assert by["B01_read_ptr_no_inc"].line == 33
    assert by["B16_no_empty_guard"].outcome == "survived"
    assert by["B17_both_ignored_at_7"].outcome == "invalid"
    assert by["E01_dead_full_branch"].outcome == "equivalent_ok"


def test_evaluate_aborts_when_golden_is_not_pass(bugs, tmp_path):
    """골든이 PASS가 아니면 변형을 실행하지 않고 중단 표시를 한다."""
    calls = []

    def runner(files, top, workdir):
        calls.append(workdir)
        return _j("FAIL", "FAIL", wd=workdir)

    rep = evaluate(bugs, GOLDEN, TB, TOP, runner, tmp_path)
    assert rep.aborted and rep.results == [] and len(calls) == 1
    assert rep.golden["status"] == "FAIL"


def test_runner_receives_mutated_rtl_and_the_tb(bugs, tmp_path):
    """변형 실행에는 패치된 RTL과 TB가 들어가고, 골든 원본은 바뀌지 않는다."""
    seen = {}
    golden_before = (GOLDEN / "fifo_ctrl.v").read_bytes()

    def runner(files, top, workdir):
        if Path(workdir).parent.name == "B07_full_at_7":
            seen["files"] = files
        return _j("PASS", "PASS", wd=workdir)

    evaluate([b for b in bugs if b.id == "B07_full_at_7"], GOLDEN, TB, TOP, runner, tmp_path)
    ctrl = next(f for f in seen["files"] if f.endswith("fifo_ctrl.v"))
    assert "count == 7)" in Path(ctrl).read_text(encoding="utf-8")
    assert seen["files"][-1] == str(TB)
    assert (GOLDEN / "fifo_ctrl.v").read_bytes() == golden_before


def test_summarize_excludes_invalid_and_equivalent_from_score():
    """mutation score = detected / (detected + survived). invalid와 동등 변형은 분모에서 뺀다."""
    def r(i, t, o, eq=False):
        return BugResult(i, t, eq, o, "X", None, 1)
    s = summarize([r("a", "pointer", "detected"), r("b", "pointer", "detected"),
                   r("c", "guard", "survived"), r("d", "flag", "invalid"),
                   r("e", "pointer", "equivalent_ok", True),
                   r("f", "pointer", "equivalent_unexpected_detect", True)])
    assert s["mutation_score"] == pytest.approx(2 / 3)
    assert s["by_type"] == {"pointer": {"detected": 2, "survived": 0}, "guard": {"detected": 0, "survived": 1}}
    assert s["survivors"] == ["c"] and s["problems"] == ["d", "f"]
    assert summarize([])["mutation_score"] is None


def test_report_is_json_serializable(bugs, tmp_path):
    """결과 리포트는 JSON으로 저장 가능하고 summary가 포함된다."""
    rep = evaluate(bugs[:2], GOLDEN, TB, TOP, lambda f, t, w: _j("FAIL", "FAIL", wd=w) if "golden" not in w
                   else _j("PASS", "PASS", wd=w), tmp_path)
    d = json.loads(json.dumps(rep.to_dict()))
    assert d["summary"]["total"] == 2 and d["aborted"] is False and len(d["results"]) == 2