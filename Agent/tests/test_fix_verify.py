"""Phase 7-5: 수정안 재시뮬레이션 (가짜 Runner + 가짜 LLM, Vivado/네트워크 불필요).

확인 사항
- 수정안 적용은 원본을 바꾸지 않고, find가 정확히 한 번이 아니면 거부한다.
- `rerun_sim` 도구는 sim 함수가 있을 때만 노출되고, 같은 제안은 다시 돌리지 않으며, 횟수 상한이 있다.
- 수정안 분류(fixed_golden / fixed_pass / still_fail / unverified / no_fix)가 규칙대로 나온다.
- 평가 하네스가 보고서의 수정안을 사후 검증해 Case.fix, 요약, 리포트에 싣는다.
- 도구가 꺼져 있으면 시스템 프롬프트에 7번 규칙이 들어가지 않는다 (이전 실행과 같은 조건 유지).
"""

import json

import pytest

from core.bugs import Bug
from core.debug_eval import Case, render_markdown, run_debug_eval, summarize_cases
from core.debug_protocol import build_system_prompt
from core.debug_tools import (MAX_SIM_RUNS, DebugWorkspace, FixApplyError, apply_proposal, dispatch_debug,
                              tool_specs)
from core.evaluator import Judged
from core.fix_verify import (FixResult, check_fix, equals_golden, make_sim_fn, sim_summary)
from llm import FakeLLM, LLMClient

GOLDEN_A = "module a(input x, output y);\n  assign y = x;\nendmodule\n"
GOLDEN_B = "module b(input x, output y);\n  assign y = ~x;\nendmodule\n"
BUGGY_A = "module a(input x, output y);\n  assign y = ~x;\nendmodule\n"
TB = "module tb;\nendmodule\n"
FAIL_LOG = "CHECK_FAIL t=27 ns sig=y exp=1 got=0\nCHECK_FAIL t=30 ns sig=y exp=0 got=1\nCHECKS total=10 mismatches=2\n[TB] FAIL: 2\n"


class Runner:
    """파일 내용으로 판정하는 가짜 Runner: a.v에 '~'가 있거나 b.v에 '~'가 없으면 FAIL (골든은 PASS)."""

    def __init__(self):
        self.calls = []

    def __call__(self, files, top, workdir):
        self.calls.append((list(files), top, workdir))
        text = {f.replace("\\", "/").rsplit("/", 1)[-1]: open(f, encoding="utf-8").read()
                for f in files if f.endswith((".v",)) and "tb.v" not in f}
        bad = ("~" in text.get("a.v", "")) or ("~" not in text.get("b.v", "~"))
        return Judged("FAIL" if bad else "PASS", "FAIL" if bad else "PASS", FAIL_LOG if bad else "", 0.1, workdir, None)


def mk_ws(sim=None):
    ws = DebugWorkspace({"rtl/a.v": BUGGY_A, "rtl/b.v": GOLDEN_B}, {"tb/tb.v": TB}, "log")
    ws.sim = sim
    return ws


def fake_sim(status="PASS"):
    calls = []

    def sim(rtl):
        calls.append(dict(rtl))
        return {"status": status, "tb_verdict": status, "n_check_fails": 0 if status == "PASS" else 2,
                "checks_total": 10, "mismatches": 0, "first_failures": []}
    sim.calls = calls
    return sim


FIX = {"id": 1, "file": "rtl/a.v", "line": 2, "find": "assign y = ~x;", "replace": "assign y = x;"}
GOLDEN = {"rtl/a.v": GOLDEN_A, "rtl/b.v": GOLDEN_B}
BUGGY = {"rtl/a.v": BUGGY_A, "rtl/b.v": GOLDEN_B}


# ---------------------------------------------------------------------------------------------
# apply_proposal / equals_golden / sim_summary
# ---------------------------------------------------------------------------------------------
def test_수정안_적용은_원본을_바꾸지_않는다():
    """적용 결과는 새 dict이고, 원본 dict와 다른 파일은 그대로다."""
    out = apply_proposal(BUGGY, "rtl/a.v", "assign y = ~x;", "assign y = x;")
    assert out["rtl/a.v"] == GOLDEN_A and out["rtl/b.v"] == GOLDEN_B
    assert BUGGY["rtl/a.v"] == BUGGY_A


@pytest.mark.parametrize("file,find", [("rtl/zz.v", "x"), ("rtl/a.v", "없는 텍스트"), ("rtl/a.v", ""), ("rtl/a.v", "y")])
def test_수정안_적용_거부(file, find):
    """파일이 없거나 find가 비었거나 0번/여러 번 나타나면 적용하지 않고 오류를 낸다 ('y'는 a.v에 여러 번 나온다)."""
    with pytest.raises(FixApplyError):
        apply_proposal(BUGGY, file, find, "z")


def test_골든_비교는_주석과_공백을_무시한다():
    """주석과 공백만 다르면 같은 것으로, 코드가 다르면 다른 것으로 본다."""
    same = {"rtl/a.v": "module a(input x,output y);\n// 주석\nassign   y=x ;  /* c */\nendmodule\n", "rtl/b.v": GOLDEN_B}
    assert equals_golden(same, GOLDEN)
    assert not equals_golden(BUGGY, GOLDEN)
    assert not equals_golden({"rtl/a.v": GOLDEN_A}, GOLDEN)         # 파일 집합이 다르면 다름


def test_시뮬레이션_요약은_실패_개수와_앞쪽_실패만_담는다():
    """로그 전체가 아니라 상태, 실패 개수, 앞쪽 실패 몇 개만 요약한다."""
    s = sim_summary(Judged("FAIL", "FAIL", FAIL_LOG, 0.1, "w"))
    assert s["status"] == "FAIL" and s["n_check_fails"] == 2 and s["checks_total"] == 10 and s["mismatches"] == 2
    assert s["first_failures"][0] == {"t_ps": 27000, "signal": "y", "expected": "1", "got": "0"}
    p = sim_summary(Judged("PASS", "PASS", "", 0.1, "w"))
    assert p["n_check_fails"] == 0 and p["first_failures"] == []


def test_make_sim_fn은_호출마다_새_폴더에_쓰고_TB를_넘긴다(tmp_path):
    """수정된 RTL을 파일 이름(basename)으로 쓰고, 원본 TB와 함께 Runner를 부른다. 폴더는 호출마다 달라야 한다 (xsim은 기존 폴더를 거부)."""
    r = Runner()
    sim = make_sim_fn(r, [tmp_path / "tb.v"], "tb", tmp_path / "w")
    assert sim(GOLDEN)["status"] == "PASS"
    assert sim(BUGGY)["status"] == "FAIL"
    (files1, top1, wd1), (files2, _, wd2) = r.calls
    assert top1 == "tb" and files1[-1].endswith("tb.v") and files1[0].endswith("a.v")
    assert wd1 != wd2 and (tmp_path / "w" / "sim1" / "rtl" / "a.v").read_text() == GOLDEN_A


# ---------------------------------------------------------------------------------------------
# rerun_sim 도구
# ---------------------------------------------------------------------------------------------
def test_rerun_sim은_sim이_있을_때만_노출된다():
    """sim 함수가 없으면 도구 명세에도 없고 호출하면 알 수 없는 도구 오류다."""
    assert "rerun_sim" not in {s["name"] for s in tool_specs(mk_ws())}
    assert "알 수 없는 도구" in dispatch_debug(mk_ws(), "rerun_sim", {"proposal_id": 1})["error"]
    assert "rerun_sim" in {s["name"] for s in tool_specs(mk_ws(fake_sim()))}


def test_rerun_sim은_저장된_수정안을_복사본에_적용한다():
    """propose_fix로 저장한 제안만 돌릴 수 있고, 작업 공간의 RTL 원본은 바뀌지 않으며 sim에는 수정된 RTL이 간다."""
    sim = fake_sim()
    ws = mk_ws(sim)
    assert "error" in dispatch_debug(ws, "rerun_sim", {"proposal_id": 1})          # 아직 제안 없음
    pid = dispatch_debug(ws, "propose_fix", {"file": "rtl/a.v", "find": "assign y = ~x;", "replace": "assign y = x;"})["proposal_id"]
    r = dispatch_debug(ws, "rerun_sim", {"proposal_id": pid})
    assert r["status"] == "PASS" and r["proposal_id"] == pid
    assert sim.calls[0]["rtl/a.v"] == GOLDEN_A and ws.rtl["rtl/a.v"] == BUGGY_A


def test_rerun_sim은_같은_제안을_다시_돌리지_않고_상한이_있다():
    """같은 제안은 캐시된 결과(cached)를 주고 횟수를 쓰지 않는다. 서로 다른 제안은 MAX_SIM_RUNS번까지만 돈다."""
    sim = fake_sim("FAIL")
    ws = mk_ws(sim)
    ids = []
    for i in range(MAX_SIM_RUNS + 1):
        ids.append(dispatch_debug(ws, "propose_fix", {"file": "rtl/a.v", "find": "assign y = ~x;",
                                                      "replace": f"assign y = ~x | 1'b{i % 2} & x[{i}];"})["proposal_id"])
    first = dispatch_debug(ws, "rerun_sim", {"proposal_id": ids[0]})
    again = dispatch_debug(ws, "rerun_sim", {"proposal_id": ids[0]})
    assert again["cached"] is True and again["status"] == first["status"] and len(sim.calls) == 1
    for i in ids[1:MAX_SIM_RUNS]:
        assert "error" not in dispatch_debug(ws, "rerun_sim", {"proposal_id": i})
    over = dispatch_debug(ws, "rerun_sim", {"proposal_id": ids[MAX_SIM_RUNS]})
    assert "최대" in over["error"] and len(sim.calls) == MAX_SIM_RUNS


def test_rerun_sim_내부_오류는_루프를_죽이지_않는다():
    """sim이 예외를 던져도 {"error": ...}로 돌아온다."""
    def boom(rtl):
        raise FileNotFoundError("xvlog")
    ws = mk_ws(boom)
    pid = dispatch_debug(ws, "propose_fix", {"file": "rtl/a.v", "find": "assign y = ~x;", "replace": "assign y = x;"})["proposal_id"]
    assert "FileNotFoundError" in dispatch_debug(ws, "rerun_sim", {"proposal_id": pid})["error"]


def test_프롬프트의_rerun_sim_규칙은_도구가_있을_때만_들어간다():
    """도구가 없으면 시스템 프롬프트는 규칙 7번과 rerun_sim 언급이 없다 (이전 실행과 같은 조건). 있으면 둘 다 들어간다."""
    off = build_system_prompt(tool_specs(mk_ws()))
    on = build_system_prompt(tool_specs(mk_ws(fake_sim())))
    assert "rerun_sim" not in off and "7. After propose_fix" not in off
    assert "rerun_sim" in on and "7. After propose_fix" in on and "only if rerun_sim returned PASS" in on


# ---------------------------------------------------------------------------------------------
# check_fix 분류
# ---------------------------------------------------------------------------------------------
def rep_ids(*ids):
    return {"verdict": "rtl_bug", "fix_proposal_ids": list(ids)}


def run_check(report, proposals, tmp_path):
    return check_fix(report, proposals, BUGGY, GOLDEN, make_sim_fn(Runner(), [tmp_path / "tb.v"], "tb", tmp_path / "w"))


def test_수정안_분류_골든과_같음(tmp_path):
    """원래 코드로 되돌리면 PASS이고 골든과 같다 -> fixed_golden."""
    r = run_check(rep_ids(1), [FIX], tmp_path)
    assert r.category == "fixed_golden" and r.results[0]["equals_golden"] is True and r.claimed_ids == [1]


def test_수정안_분류_PASS이지만_골든과_다름(tmp_path):
    """TB가 통과시키지만 골든과 다른 수정은 fixed_pass로 따로 센다 (대안 수정인지 TB 구멍인지 사람이 diff로 판단)."""
    alt = {**FIX, "replace": "assign y = x & 1'b1;"}
    r = run_check(rep_ids(1), [alt], tmp_path)
    assert r.category == "fixed_pass" and r.results[0]["equals_golden"] is False


def test_수정안_분류_적용해도_FAIL(tmp_path):
    """여전히 '~'가 있는 수정은 시뮬레이션이 FAIL이다 -> still_fail."""
    bad = {**FIX, "replace": "assign y = ~x | 1'b0;"}
    assert run_check(rep_ids(1), [bad], tmp_path).category == "still_fail"


def test_수정안_분류_여러_제안_중_하나라도_골든이면_fixed_golden(tmp_path):
    """제안이 둘이고 하나만 맞아도 맞은 쪽이 우선한다. 틀린 제안 결과도 results에 남는다."""
    bad = {**FIX, "id": 2, "replace": "assign y = ~x | 1'b0;"}
    r = run_check(rep_ids(2, 1), [FIX, bad], tmp_path)
    assert r.category == "fixed_golden" and [x["status"] for x in r.results] == ["FAIL", "PASS"]


@pytest.mark.parametrize("report", [None, {"verdict": "rtl_bug"}, rep_ids(), rep_ids(99), {"fix_proposal_ids": ["1"]}])
def test_수정안_분류_no_fix(report, tmp_path):
    """보고서가 없거나, ids가 비었거나, 저장된 제안에 없는 id뿐이거나, 정수가 아니면 no_fix. 시뮬레이션도 돌리지 않는다."""
    r = Runner()
    out = check_fix(report, [FIX], BUGGY, GOLDEN, make_sim_fn(r, [tmp_path / "tb.v"], "tb", tmp_path / "w"))
    assert out.category == "no_fix" and not r.calls


def test_수정안_분류_적용_불가와_시뮬레이션_실패는_unverified(tmp_path):
    """find가 원본에 없으면 apply_error, sim이 예외를 던지면 sim_error. 둘 다 still_fail이 아니라 unverified다."""
    gone = {**FIX, "find": "없는 텍스트"}
    r1 = run_check(rep_ids(1), [gone], tmp_path)
    assert r1.category == "unverified" and r1.results[0]["status"] == "apply_error"

    def boom(rtl):
        raise RuntimeError("xsim died")
    r2 = check_fix(rep_ids(1), [FIX], BUGGY, GOLDEN, boom)
    assert r2.category == "unverified" and r2.results[0]["status"] == "sim_error"


def test_중복_id는_한_번만_검증한다(tmp_path):
    """보고서가 같은 id를 두 번 적어도 시뮬레이션은 한 번이다."""
    r = Runner()
    check_fix(rep_ids(1, 1), [FIX], BUGGY, GOLDEN, make_sim_fn(r, [tmp_path / "tb.v"], "tb", tmp_path / "w"))
    assert len(r.calls) == 1


# ---------------------------------------------------------------------------------------------
# 평가 하네스 통합
# ---------------------------------------------------------------------------------------------
def tool(name, **a):
    return json.dumps({"thought": "t", "action": "tool", "tool": name, "args": a})


def final(file, line, ids=()):
    rep = {"verdict": "rtl_bug", "location": {"file": file, "line": line}, "summary": "s", "root_cause": "c",
           "evidence": [{"step": 1, "observation": "o"}], "fix_proposal_ids": list(ids), "confidence": "high"}
    return json.dumps({"thought": "d", "action": "final", "report": rep})


@pytest.fixture
def env(tmp_path):
    g = tmp_path / "golden" / "rtl"
    g.mkdir(parents=True)
    (g / "a.v").write_text(GOLDEN_A)
    (g / "b.v").write_text(GOLDEN_B)
    tb = tmp_path / "tb.v"
    tb.write_text(TB)
    bugs = [Bug("B01", "dut", "pointer", "a.v", "assign y = x;", "assign y = ~x;", 1, 1, "SECRET", False),
            Bug("B02", "dut", "flag", "b.v", "assign y = ~x;", "assign y = x;", 1, 1, "SECRET", False)]
    return g, tb, bugs, tmp_path


def go(env, responses, **kw):
    g, tb, bugs, tmp = env
    runner = Runner()
    rep = run_debug_eval(bugs, g, tb, "tb", "dut", runner, LLMClient(FakeLLM(responses)), tmp / "out", dut="dut", **kw)
    return rep, runner


FLOW = [tool("propose_fix", file="rtl/a.v", find="assign y = ~x;", replace="assign y = x;"),
        tool("rerun_sim", proposal_id=1),
        final("rtl/a.v", 2, ids=[1]),
        tool("read_rtl", file="rtl/b.v"),
        final("rtl/b.v", 2)]


def test_하네스는_수정안을_사후_검증하고_기록한다(env):
    """B01은 맞는 수정을 보고하고 B02는 수정안이 없다. Case.fix에 분류와 Agent가 직접 돌린 시뮬레이션 결과가 남는다."""
    rep, runner = go(env, FLOW, sim_tool=True, verify_fixes=True)
    c1, c2 = rep.cases
    assert c1.fix["category"] == "fixed_golden" and c1.fix["agent_sims"] == {"1": "PASS"}
    assert c2.fix["category"] == "no_fix" and c2.fix["agent_sims"] == {}
    s = rep.summary
    assert s["n_fix_verified"] == 2 and s["fix_categories"]["fixed_golden"] == 1 and s["fix_categories"]["no_fix"] == 1
    assert s["fix_golden_rate"] == 0.5 and s["agent_sim_runs"] == 1 and s["located_but_not_fixed"] == ["B02"]
    md = render_markdown(rep, "t")
    assert "### 수정안 검증 (7-5)" in md and "fixed_golden" in md and "| 수정안 |" in md


def test_하네스_기본값은_이전_조건과_같다(env):
    """sim_tool/verify_fixes를 켜지 않으면 rerun_sim 도구도 사후 검증도 없고, 요약에 수정안 표가 나오지 않는다."""
    rep, runner = go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2),
                           tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    assert all(c.fix is None for c in rep.cases) and rep.summary["n_fix_verified"] == 0
    assert "수정안 검증 (7-5)" not in render_markdown(rep)
    assert len(runner.calls) == 2                                   # 변형 실행만 (검증 시뮬레이션 없음)


def test_사후_검증은_Agent의_주장과_무관하게_원본_TB로_다시_돌린다(env):
    """Agent가 rerun_sim을 쓰지 않아도 보고서가 지목한 수정안은 사후에 시뮬레이션된다. 틀린 수정이면 still_fail."""
    flow = [tool("propose_fix", file="rtl/a.v", find="assign y = ~x;", replace="assign y = ~x | 1'b0;"),
            final("rtl/a.v", 2, ids=[1]),
            tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)]
    rep, runner = go(env, flow, sim_tool=True, verify_fixes=True)
    assert rep.cases[0].fix["category"] == "still_fail" and rep.cases[0].fix["agent_sims"] == {}
    assert rep.cases[0].score["category"] == "exact"                # 위치는 맞아도 수정은 실패한 케이스
    assert rep.summary["located_but_not_fixed"] == ["B01", "B02"]     # B02는 위치만 맞고 수정안이 없다


def test_Case_fix는_저장과_이어하기에서_보존된다(env):
    """cases/<id>.json에 fix가 저장되고 resume으로 불러와도 같다. 옛 형식(fix 없음)은 None으로 읽는다."""
    rep, _ = go(env, FLOW, sim_tool=True, verify_fixes=True)
    d = rep.cases[0].to_dict()
    assert Case.from_dict(d).fix == d["fix"]
    old = {k: v for k, v in d.items() if k != "fix"}
    assert Case.from_dict(old).fix is None
    assert summarize_cases([Case.from_dict(old)])["n_fix_verified"] == 0


# ---------------------------------------------------------------------------------------------
# 사후 검증 스크립트 (scripts/verify_fixes.py)
# ---------------------------------------------------------------------------------------------
def test_verify_fixes_스크립트는_저장된_결과를_LLM_없이_검증한다(tmp_path, monkeypatch):
    """results의 cases/*.json에서 보고서와 제안을 읽어 변형을 다시 만들고 검증한다. 원본 케이스 파일은 바꾸지 않고 fix_check.json과 리포트를 쓴다."""
    from scripts import verify_fixes as vf
    g = tmp_path / "dut" / "rtl"
    g.mkdir(parents=True)
    (g / "a.v").write_text(GOLDEN_A)
    (g / "b.v").write_text(GOLDEN_B)
    (g.parent / "tb").mkdir()
    (g.parent / "tb" / "tb_sync_fifo_sc.v").write_text(TB)
    cat = tmp_path / "bugs.json"
    cat.write_text(json.dumps({"dut": "dut", "golden_rtl": str(g), "top": "tb", "bugs": [
        {"id": "B01", "dut": "dut", "type": "pointer", "file": "a.v", "find": "assign y = x;",
         "replace": "assign y = ~x;", "expect_count": 1, "description": "d", "equivalent": False}]}), encoding="utf-8")
    res = tmp_path / "runs" / "dbgeval_t_1"
    (res / "work" / "cases").mkdir(parents=True)          # run_debug_eval의 실제 저장 위치
    case = {"bug_id": "B01", "type": "pointer", "outcome": "evaluated", "score": {"category": "exact"},
            "run": {"report": rep_ids(1), "proposals": [FIX]}}
    (res / "work" / "cases" / "B01.json").write_text(json.dumps(case), encoding="utf-8")
    before = (res / "work" / "cases" / "B01.json").read_text(encoding="utf-8")
    monkeypatch.setattr(vf, "ROOT", tmp_path)
    rc = vf.main(["--catalog", str(cat), "--results", str(res)], runner=Runner())
    assert rc == 0
    out = json.loads((res / "fix_check.json").read_text(encoding="utf-8"))
    assert out["categories"]["fixed_golden"] == 1 and out["cases"][0]["fix"]["category"] == "fixed_golden"
    assert (res / "work" / "cases" / "B01.json").read_text(encoding="utf-8") == before
    assert list((tmp_path / "reports").glob("fix_check_dut_*.md"))


def test_verify_fixes_결과_폴더가_없으면_종료코드_2(tmp_path, monkeypatch):
    """결과 폴더를 찾지 못하면 안내하고 2로 끝난다."""
    from scripts import verify_fixes as vf
    cat = tmp_path / "bugs.json"
    cat.write_text(json.dumps({"dut": "dut", "golden_rtl": "g", "top": "tb", "bugs": []}), encoding="utf-8")
    monkeypatch.setattr(vf, "ROOT", tmp_path)
    assert vf.main(["--catalog", str(cat), "--label", "nope"], runner=Runner()) == 2


# ---------------------------------------------------------------------------------------------
# 도구 사용 분포 지표
# ---------------------------------------------------------------------------------------------
def test_도구_사용_분포와_증거_도구_사용_케이스_집계(env):
    """B01은 read_rtl만, B02는 read_tb와 get_log_snippet까지 쓴다. 도구별 호출 수와 증거 도구를 쓴 케이스가 집계되고 리포트에 나온다 (list_signals/read_rtl은 증거 도구가 아니다)."""
    flow = [tool("read_rtl", file="rtl/a.v"), tool("list_signals"), final("rtl/a.v", 2),
            tool("read_tb", file="tb/tb.v"), tool("get_log_snippet", pattern="CHECK"), final("rtl/b.v", 2)]
    rep, _ = go(env, flow)
    s = rep.summary
    assert s["tool_usage"] == {"get_log_snippet": 1, "list_signals": 1, "read_rtl": 1, "read_tb": 1}
    assert s["evidence_tool_cases"] == ["B02"]
    md = render_markdown(rep)
    assert "### 도구 사용" in md and "| read_rtl | 1 |" in md and "쓴 케이스: 1/2" in md


def test_증거_도구를_안_쓰면_빈_목록(env):
    """read_rtl만 쓰면 evidence_tool_cases는 비어 있고 리포트에 0/N으로 나온다."""
    rep, _ = go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2),
                      tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    assert rep.summary["evidence_tool_cases"] == [] and "쓴 케이스: 0/2" in render_markdown(rep)
