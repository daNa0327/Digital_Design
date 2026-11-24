"""Phase 7-4: Debug Agent 평가 하네스 (가짜 Runner + 가짜 LLM, Vivado/네트워크 불필요).

확인 사항
- 정답 대조 분류(exact/near/wrong_line/wrong_file/not_rtl_bug/no_report)가 규칙대로 나온다.
- Agent에게 정답 단서(변형 ID, 카탈로그 설명, 실제 경로)가 전달되지 않는다.
- 한도로 중간에 멈추면 이후는 미실행으로 남고, resume이 끝난 케이스만 건너뛴다.
"""

import json

import pytest

from core.bugs import Bug, apply_bug
from core.debug_eval import (Case, Score, Truth, default_vcd_loader, render_markdown, run_debug_eval,
                             score_case, summarize_cases)
from core.evaluator import Judged
from llm import DailyQuotaExceeded, FakeLLM, LLMClient

GOLDEN_A = "module a(input x, output y);\n  assign y = x;\n  wire q;\n  assign q = x;\nendmodule\n"
GOLDEN_B = "module b(input x, output y);\n  assign y = ~x;\nendmodule\n"
TB = "module tb;\nendmodule\n"
FAIL_LOG = "CHECK_FAIL t=27 ns sig=y exp=1 got=0\nCHECKS total=10 mismatches=1\n[TB] FAIL: 1\n"


def mk_bug(id, file, find, replace, type="pointer", eq=False, occ=1, cnt=1):
    return Bug(id, "dut", type, file, find, replace, cnt, occ, f"SECRET description of {id}", eq)


@pytest.fixture
def env(tmp_path):
    g = tmp_path / "golden" / "rtl"
    g.mkdir(parents=True)
    (g / "a.v").write_text(GOLDEN_A)
    (g / "b.v").write_text(GOLDEN_B)
    tb = tmp_path / "tb.v"
    tb.write_text(TB)
    bugs = [mk_bug("B01_first", "a.v", "assign y = x;", "assign y = ~x;"),
            mk_bug("B02_second", "b.v", "assign y = ~x;", "assign y = x;", "flag"),
            mk_bug("E01_equiv", "a.v", "assign q = x;", "assign q = x;  ", eq=True)]
    return g, tb, bugs, tmp_path


def truth_line(bug, g, tmp_path):
    return apply_bug(bug, g, tmp_path / f"_probe_{bug.id}").line


def tool(name, **a):
    return json.dumps({"thought": "t", "action": "tool", "tool": name, "args": a})


def final(file, line, conf="high"):
    rep = {"verdict": "rtl_bug", "location": {"file": file, "line": line}, "summary": "s", "root_cause": "c",
           "evidence": [{"step": 1, "observation": "o"}], "fix_proposal_ids": [], "confidence": conf}
    return json.dumps({"thought": "d", "action": "final", "report": rep})


class Runner:
    """변형마다 정해 둔 상태를 돌려주는 가짜 Runner. 호출 기록을 남긴다."""

    def __init__(self, status_by_marker=None):
        self.calls = []
        self.status_by_marker = status_by_marker or {}

    def __call__(self, files, top, workdir):
        self.calls.append((list(files), top, workdir))
        status = "FAIL"
        for marker, st in self.status_by_marker.items():
            if marker in workdir:
                status = st
        return Judged(status, "FAIL" if status == "FAIL" else None, FAIL_LOG if status == "FAIL" else "",
                      0.1, workdir, None)


def go(env, responses, runner=None, **kw):
    g, tb, bugs, tmp = env
    fake = FakeLLM(responses)
    runner = runner or Runner()
    rep = run_debug_eval(bugs, g, tb, "tb", "dut", runner, LLMClient(fake), tmp / "out", dut="dut", **kw)
    return rep, fake, runner


# ---------------------------------------------------------------------------------------------
# score_case
# ---------------------------------------------------------------------------------------------
T = Truth("B", "pointer", "rtl/a.v", 10)


def rep(verdict="rtl_bug", file="rtl/a.v", line=10, conf="high"):
    return {"verdict": verdict, "location": {"file": file, "line": line}, "confidence": conf}


@pytest.mark.parametrize("report,cat,delta", [
    (None, "no_report", None),
    (rep("tb_issue"), "not_rtl_bug", None),
    (rep("unknown"), "not_rtl_bug", None),
    (rep(file="rtl/b.v"), "wrong_file", None),
    (rep(line=10), "exact", 0),
    (rep(line=12), "near", 2),
    (rep(line=8), "near", 2),
    (rep(line=13), "wrong_line", 3),
    (rep(line=1), "wrong_line", 9),
])
def test_정답_대조_분류(report, cat, delta):
    """보고서가 없거나 rtl_bug가 아니면 위치를 보지 않고, 파일이 다르면 wrong_file, 같은 파일이면 줄 차이(±2 이내 near)로 가른다."""
    s = score_case(report, T, near=2)
    assert s.category == cat and s.line_delta == delta
    assert s.located == (cat in ("exact", "near"))


def test_near_허용_오차는_조절된다():
    """허용 오차를 0으로 하면 정확한 줄만 맞는 것으로 본다."""
    assert score_case(rep(line=11), T, near=0).category == "wrong_line"
    assert score_case(rep(line=11), T, near=1).category == "near"


# ---------------------------------------------------------------------------------------------
# run_debug_eval
# ---------------------------------------------------------------------------------------------
def test_정상_평가_흐름과_분류(env):
    """B01은 정확히, B02는 다른 파일을 지목한다. 동등 변형은 건너뛰고 Agent를 부르지 않는다."""
    g, tb, bugs, tmp = env
    l1 = truth_line(bugs[0], g, tmp)
    report, fake, runner = go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", l1),
                                    tool("read_rtl", file="rtl/b.v"), final("rtl/a.v", 2, conf="low")])
    cats = {c.bug_id: (c.outcome, c.score["category"] if c.score else None) for c in report.cases}
    assert cats == {"B01_first": ("evaluated", "exact"), "B02_second": ("evaluated", "wrong_file"),
                    "E01_equiv": ("equivalent_skipped", None)}
    assert len(runner.calls) == 2 and len(fake.calls) == 4              # 동등 변형은 실행도 안 함
    s = report.summary
    assert s["n_evaluated"] == 2 and s["exact_rate"] == 0.5 and s["located_rate"] == 0.5
    assert s["llm_calls"] == 4 and s["mean_steps_final"] == 2


def test_사람_TB가_FAIL시키지_못한_변형은_Agent를_부르지_않는다(env):
    """변형 실행이 PASS면 평가 대상이 아니다 (not_failed). 이때 LLM 호출은 0회다."""
    report, fake, _ = go(env, [], runner=Runner({"B01_first": "PASS", "B02_second": "COMPILE_ERROR"}))
    assert [c.outcome for c in report.cases] == ["not_failed", "not_failed", "equivalent_skipped"]
    assert fake.calls == [] and report.summary["n_evaluated"] == 0
    assert report.summary["n_not_failed"] == 2 and report.summary["exact_rate"] is None


def test_Agent에게_정답_단서가_전달되지_않는다(env):
    """변형 ID, 카탈로그 설명(description), 변형 폴더 경로가 어떤 프롬프트에도 들어가지 않는다."""
    g, tb, bugs, tmp = env
    report, fake, _ = go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2),
                               tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    blob = "\n".join((c.system or "") + c.prompt for c in fake.calls)
    for secret in ("B01_first", "B02_second", "SECRET", "E01", "golden", str(tmp)):
        assert secret not in blob, secret


def test_Agent이_보는_RTL은_변형본이다(env):
    """Agent가 읽는 RTL에는 패치가 반영돼 있다 (골든이 아니라 변형을 디버그해야 한다)."""
    report, fake, _ = go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2),
                               tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    assert "assign y = ~x;" in fake.calls[1].prompt          # B01: x -> ~x 로 바뀐 줄
    assert "assign y = x;" in fake.calls[3].prompt           # B02: ~x -> x


def test_한도로_멈추면_이후_케이스는_미실행(env):
    """두 번째 케이스에서 일일 한도가 소진되면 그 케이스는 quota로 기록하고, 이후는 not_run으로 남긴다."""
    g, tb, bugs, tmp = env
    extra = bugs[:2] + [mk_bug("B03_third", "b.v", "assign y = ~x;", "assign y = 1'b0;", "reset")]
    fake = FakeLLM([tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2), DailyQuotaExceeded("일일 한도")])
    runner = Runner()
    report = run_debug_eval(extra, g, tb, "tb", "dut", runner, LLMClient(fake), tmp / "out2", dut="dut")
    assert [c.outcome for c in report.cases] == ["evaluated", "evaluated", "not_run"]
    assert report.cases[1].run["status"] == "quota" and report.aborted_reason.startswith("B02_second: quota")
    assert len(runner.calls) == 2                             # 세 번째 변형은 시뮬레이션도 하지 않음
    assert report.summary["n_not_run"] == 1


def test_resume은_끝난_케이스만_건너뛴다(env):
    """quota로 끝난 케이스는 다시 실행하고(이전 작업 폴더가 남아 있어도 오류 없이), 정상 종료한 케이스는 저장된 결과를 쓴다."""
    g, tb, bugs, tmp = env
    two = bugs[:2]
    l1 = truth_line(bugs[0], g, tmp)
    fake1 = FakeLLM([tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", l1), DailyQuotaExceeded("한도")])
    r1 = run_debug_eval(two, g, tb, "tb", "dut", Runner(), LLMClient(fake1), tmp / "o", dut="dut")
    assert r1.cases[1].run["status"] == "quota" and (tmp / "o" / "B02_second").exists()
    fake2, runner2 = FakeLLM([tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)]), Runner()
    r2 = run_debug_eval(two, g, tb, "tb", "dut", runner2, LLMClient(fake2), tmp / "o", dut="dut", resume=True)
    assert r2.cases[0].resumed and r2.cases[0].score["category"] == "exact"
    assert not r2.cases[1].resumed and r2.cases[1].run["status"] == "final"
    assert len(runner2.calls) == 1 and len(fake2.calls) == 2           # B01은 시뮬레이션도 LLM도 쓰지 않음
    assert r2.aborted_reason is None


def test_resume이_아니면_같은_폴더여도_처음부터_다시_실행한다(env):
    """resume이 없으면 저장된 결과를 쓰지 않고 새로 실행한다 (옛 결과가 새 결과로 둔갑하지 않게)."""
    g, tb, bugs, tmp = env
    one = bugs[:1]
    r1 = run_debug_eval(one, g, tb, "tb", "dut", Runner(), LLMClient(FakeLLM([tool("read_rtl", file="rtl/a.v"),
                        final("rtl/a.v", 40)])), tmp / "o", dut="dut")
    f2 = FakeLLM([tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2)])
    r2 = run_debug_eval(one, g, tb, "tb", "dut", Runner(), LLMClient(f2), tmp / "o", dut="dut")
    assert r1.cases[0].run["rejected_reports"] == 1              # 40번 줄은 없는 줄이라 거부됐음
    assert len(f2.calls) == 2 and not r2.cases[0].resumed


def test_케이스_파일이_저장된다(env):
    """케이스마다 cases/<id>.json이 저장되어 이어하기와 사후 분석에 쓸 수 있다."""
    g, tb, bugs, tmp = env
    go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2), tool("read_rtl", file="rtl/b.v"),
             final("rtl/b.v", 2)])
    d = json.loads((tmp / "out" / "cases" / "B01_first.json").read_text(encoding="utf-8"))
    assert d["outcome"] == "evaluated" and d["truth"]["file"] == "rtl/a.v" and d["run"]["status"] == "final"
    assert not (tmp / "out" / "cases" / "E01_equiv.json").exists()          # 동등 변형은 저장하지 않음


def test_VCD_로더가_None이면_VCD_도구_없이_진행된다(env):
    """VCD가 없는 실행(경로 없음, 읽기 실패)에서도 평가가 죽지 않고, Agent는 VCD 도구를 안내받지 않는다."""
    assert default_vcd_loader(None) is None and default_vcd_loader("/no/such/file.vcd") is None
    report, fake, _ = go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2),
                               tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    assert report.summary["n_evaluated"] == 2
    assert "read_vcd_signal" not in (fake.calls[0].system or "")


def test_VCD_파서가_예외를_내도_None(tmp_path, monkeypatch):
    """VCD 파싱 중 예외가 나면 삼키고 None을 돌려준다 (Agent는 VCD 없이 진행)."""
    from core.vcd_reader import VcdReader

    def boom(*a, **k):
        raise ValueError("깨진 VCD")

    monkeypatch.setattr(VcdReader, "from_file", boom)
    f = tmp_path / "x.vcd"
    f.write_text("x")
    assert default_vcd_loader(str(f)) is None


def test_VCD가_있으면_Agent가_VCD_도구를_안내받는다(env):
    """로더가 VcdTools를 돌려주면 시스템 프롬프트에 VCD 도구가 나타난다."""
    class FakeTools:
        pass

    g, tb, bugs, tmp = env
    fake = FakeLLM([tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2)])
    run_debug_eval(bugs[:1], g, tb, "tb", "dut", Runner(), LLMClient(fake), tmp / "v", dut="dut",
                   vcd_loader=lambda p: FakeTools())
    assert "read_vcd_signal" in fake.calls[0].system


# ---------------------------------------------------------------------------------------------
# 집계와 리포트
# ---------------------------------------------------------------------------------------------
def make_case(id, type, cat, conf="high", status="final", steps=3, calls=3, fmt=0, rej=0, outcome="evaluated"):
    run = {"status": status, "steps": [], "n_steps": steps, "n_tool_calls": steps - 1, "llm_calls": calls, "cached_calls": 0,
           "input_tokens": 100, "output_tokens": 10, "format_errors": fmt, "rejected_reports": rej,
           "report": {"location": {"file": "rtl/a.v", "line": 3}}}
    return Case(id, type, outcome, "FAIL", {"file": "rtl/a.v", "line": 3}, run,
                {"category": cat, "confidence": conf, "verdict": "rtl_bug", "file_ok": True, "line_delta": 0})


def test_집계_지표():
    """분모는 Agent가 실행된 케이스다. 확신도 보정과 'high인데 틀림'도 집계한다."""
    cases = [make_case("B1", "pointer", "exact"), make_case("B2", "pointer", "near", conf="medium"),
             make_case("B3", "flag", "wrong_line", conf="high", fmt=1),
             make_case("B4", "flag", "no_report", status="max_steps", steps=8, calls=8, conf=None),
             Case("B5", "flag", "not_failed", "PASS"), Case("E1", "pointer", "equivalent_skipped")]
    s = summarize_cases(cases)
    assert s["n_evaluated"] == 4 and s["n_not_failed"] == 1 and s["n_equivalent_skipped"] == 1
    assert s["exact_rate"] == 0.25 and s["located_rate"] == 0.5 and s["report_rate"] == 0.75
    assert s["file_accuracy"] == 0.75                                  # exact + near + wrong_line
    assert s["mean_steps_final"] == 3 and s["mean_steps_all"] == (3 + 3 + 3 + 8) / 4
    assert s["llm_calls"] == 3 + 3 + 3 + 8
    assert s["format_error_rate"] == 1 / 17
    assert s["by_type"]["pointer"] == {"n": 2, "located": 2, "exact": 1}
    assert s["by_type"]["flag"] == {"n": 2, "located": 0, "exact": 0}
    assert s["confidence"]["high"] == {"n": 2, "located": 1} and s["high_conf_wrong"] == ["B3"]


def test_평가된_케이스가_없으면_비율은_None():
    """0으로 나누지 않고 None을 돌려준다."""
    s = summarize_cases([Case("E1", "pointer", "equivalent_skipped")])
    assert s["exact_rate"] is None and s["mean_steps_final"] is None and s["format_error_rate"] is None


def test_마크다운_리포트(env):
    """요약 표, 분류, 케이스별 표, 주의 문구가 들어가고, 중단된 평가는 경고가 붙는다."""
    from core.debug_eval import DebugEvalReport
    r = DebugEvalReport("sync_fifo", [make_case("B1", "pointer", "exact"), Case("E1", "pointer", "equivalent_skipped")],
                        meta={"tb": "tb.v", "max_steps": 8, "near": 2})
    md = render_markdown(r, "human-tb")
    assert "# Debug Agent 평가: sync_fifo (human-tb)" in md and "| **정확한 줄** | 100% |" in md
    assert "| B1 | pointer | rtl/a.v:3 | rtl/a.v:3 | exact |" in md and "해석할 때 주의" in md
    assert "중간에 멈춤" not in md
    r.aborted_reason = "B2: quota (한도)"
    md2 = render_markdown(r)
    assert "중간에 멈춤" in md2 and "--resume" in md2


# ---------------------------------------------------------------------------------------------
# 7-4 1차 실측에서 발견된 결함의 회귀 테스트
# ---------------------------------------------------------------------------------------------
class StampedRunner(Runner):
    """호출마다 로그의 시각이 달라지는 Runner (실제 xsim 로그처럼)."""

    def __call__(self, files, top, workdir):
        j = super().__call__(files, top, workdir)
        j.xsim_stdout = (f"Start of session at: Tue Nov 24 18:{len(self.calls):02d}:41 2026\n" + j.xsim_stdout
                         + f"Exiting xsim at Tue Nov 24 18:{len(self.calls):02d}:43 2026...\n")
        return j


def test_시각이_다른_로그여도_같은_실패는_캐시를_맞춘다(env, tmp_path):
    """실측 1차의 결함: 로그에 실행 시각이 들어 있어 같은 변형을 다시 돌려도 캐시가 안 맞았다.
    시각이 달라도 두 번째 평가의 실제 LLM 호출은 0회여야 한다."""
    from llm import DiskCache
    g, tb, bugs, tmp = env
    script = [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2), tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)]
    c1 = LLMClient(FakeLLM(script), cache=DiskCache(tmp_path / "cache"))
    r1 = run_debug_eval(bugs[:2], g, tb, "tb", "dut", StampedRunner(), c1, tmp / "e1", dut="dut")
    fake2 = FakeLLM([])
    r2 = run_debug_eval(bugs[:2], g, tb, "tb", "dut", StampedRunner(), LLMClient(fake2, cache=DiskCache(tmp_path / "cache")),
                        tmp / "e2", dut="dut")
    # 서로 다른 변형이 같은 첫 프롬프트를 공유하면 첫 실행에서도 캐시가 맞을 수 있으므로 "총 요청 수"로 비교한다
    total1 = r1.summary["llm_calls"] + r1.summary["cached_calls"]
    assert r1.summary["llm_calls"] >= 1 and r2.summary["llm_calls"] == 0 and r2.summary["cached_calls"] == total1
    assert fake2.calls == []


def test_STOP이_아닌_종료를_집계한다(env):
    """MAX_TOKENS 같은 종료가 몇 번 있었는지 요약과 리포트에 나온다 (빈 응답/잘린 JSON 원인 확인용)."""
    g, tb, bugs, tmp = env
    rep, _, _ = go(env, [(tool("read_rtl", file="rtl/a.v"), "MAX_TOKENS"), final("rtl/a.v", 2),
                         tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    assert rep.summary["non_stop_steps"] == 1
    assert "STOP이 아닌 이유로 끝난 응답 수 (MAX_TOKENS 등) | 1 |" in render_markdown(rep)


def test_출력_토큰_한도가_요청에_전달된다(env):
    """평가 하니스가 정한 max_output_tokens가 Agent의 모든 요청에 실린다 (기본 4096)."""
    rep, fake, _ = go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2),
                            tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    assert {c.max_output_tokens for c in fake.calls} == {4096}
    rep2, fake2, _ = go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2),
                              tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)], max_output_tokens=777)
    assert {c.max_output_tokens for c in fake2.calls} == {777}


def test_결과에_프롬프트_버전이_기록되고_섞이면_경고한다(env):
    """평가 메타에 프롬프트 해시가 남고, 케이스마다 해시가 다르면(이어하기 중 프롬프트가 바뀐 경우) 리포트가 경고한다."""
    from core.debug_eval import DebugEvalReport
    rep, _, _ = go(env, [tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2),
                         tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    assert len(rep.meta["prompt_shas"]) == 1
    md = render_markdown(rep)
    assert "프롬프트 버전(시스템 프롬프트 해시): " + rep.meta["prompt_shas"][0] in md and "프롬프트 버전이 다르다" not in md
    mixed = DebugEvalReport("d", rep.cases, meta={**rep.meta, "prompt_shas": ["aaa", "bbb"]})
    assert "케이스마다 프롬프트 버전이 다르다" in render_markdown(mixed)


def test_빈_응답_재시도가_집계되고_리포트에_나온다(env):
    """재시도 횟수와 그 덕에 단계를 이어간 횟수가 요약과 마크다운에 들어간다. 재시도는 형식 오류율을 올리지 않는다."""
    rep, fake, _ = go(env, [("", "MALFORMED_FUNCTION_CALL"), tool("read_rtl", file="rtl/a.v"), final("rtl/a.v", 2),
                            tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    s = summarize_cases(rep.cases)
    assert s["empty_retries"] == 1 and s["empty_retries_recovered"] == 1
    assert s["format_error_rate"] == 0
    assert "| 빈 응답 재시도 (보냄 / 단계를 이어간 횟수) | 1 / 1 |" in render_markdown(rep)


def test_재시도가_실패한_경우는_이어간_횟수에_세지_않는다(env):
    """재시도해도 비어서 형식 오류가 된 단계는 '보냄'에만 들어가고 '이어간 횟수'에는 들어가지 않는다. 옛 JSON(필드 없음)도 읽는다."""
    rep, _, _ = go(env, [tool("read_rtl", file="rtl/a.v"), ("", "MALFORMED_FUNCTION_CALL"),
                         ("", "MALFORMED_FUNCTION_CALL"), final("rtl/a.v", 2),
                         tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    s = summarize_cases(rep.cases)
    assert s["empty_retries"] == 1 and s["empty_retries_recovered"] == 0
    for c in rep.cases:                                                # v0a/v0b 때 저장된 JSON에는 필드가 없다
        if not c.run:                                                  # 실행되지 않은 케이스(동등 변형 등)
            continue
        c.run.pop("empty_retries", None)
        for st in c.run["steps"]:
            st.pop("retries", None)
    assert summarize_cases(rep.cases)["empty_retries"] == 0


def test_평탄한_도구_호출_정규화가_집계되고_옛_JSON도_읽는다(env):
    """정규화한 호출 수가 요약과 마크다운에 나온다. 형식 오류율은 올리지 않는다. v0a~v0c JSON(필드 없음)은 0으로 읽는다."""
    flat = json.dumps({"action": "read_rtl", "file": "rtl/a.v"})
    rep, _, _ = go(env, [flat, final("rtl/a.v", 2), tool("read_rtl", file="rtl/b.v"), final("rtl/b.v", 2)])
    s = summarize_cases(rep.cases)
    assert s["normalized_calls"] == 1 and s["format_error_rate"] == 0
    assert "| 평탄한 도구 호출 정규화 (형식 오류였을 호출) | 1 |" in render_markdown(rep)
    for c in rep.cases:
        if c.run:
            c.run.pop("normalized_calls", None)
    assert summarize_cases(rep.cases)["normalized_calls"] == 0
