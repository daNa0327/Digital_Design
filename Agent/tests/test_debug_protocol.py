"""Phase 7-2: Debug Agent 대화 규약 (파서, 보고서 검증, 프롬프트). LLM/Vivado 불필요.

핵심 확인 사항
- 파서는 형식 오류를 예외(설명 문장 포함)로 돌려주고, 펜스/잡담/여러 action 같은 흔한 출력 변형을 처리한다.
- 보고서 검증은 "근거 없는 결론"과 "없는 단계 인용"을 막는다.
- 프롬프트에 정답 단서(경로, 변형 ID)가 들어가지 않고, 캐시 키가 되도록 결정적이다.
"""

import json

import pytest

from core.debug_protocol import (Evidence, ProtocolError, Turn, build_initial_message, build_prompt,
                                 build_system_prompt, evidence_from_log, parse_action, render_turn,
                                 truncate_obs, validate_report)
from core.debug_tools import DebugWorkspace, tool_specs

RTL_FILES = ["rtl/a.v", "rtl/b.v"]


def good_report(**kw):
    r = {"verdict": "rtl_bug", "location": {"file": "rtl/a.v", "line": 7}, "summary": "s", "root_cause": "c",
         "evidence": [{"step": 1, "observation": "o"}], "fix_proposal_ids": [1], "confidence": "high"}
    r.update(kw)
    return r


# ---------------------------------------------------------------------------------------------
# parse_action
# ---------------------------------------------------------------------------------------------
def test_도구_호출_파싱():
    """기본 형식: tool 이름과 args가 그대로 나온다."""
    a = parse_action('{"thought":"t","action":"tool","tool":"read_rtl","args":{"file":"rtl/a.v"}}')
    assert (a.kind, a.tool, a.args, a.thought) == ("tool", "read_rtl", {"file": "rtl/a.v"}, "t")


def test_코드펜스_안의_JSON과_앞뒤_잡담():
    """LLM은 ```json 펜스나 설명을 덧붙이곤 한다. 그래도 action 하나를 찾아낸다."""
    txt = 'Sure, let me check.\n```json\n{"action":"tool","tool":"search_rtl","args":{"pattern":"x"}}\n```\nDone.'
    a = parse_action(txt)
    assert a.tool == "search_rtl" and a.thought == ""


def test_args_생략과_null은_빈_dict():
    """인자가 없는 도구 호출에서 args를 생략하거나 null로 줘도 된다."""
    assert parse_action('{"action":"tool","tool":"get_log_snippet"}').args == {}
    assert parse_action('{"action":"tool","tool":"get_log_snippet","args":null}').args == {}


def test_final_파싱():
    """final은 report 객체를 담는다."""
    a = parse_action(json.dumps({"action": "final", "report": good_report()}))
    assert a.kind == "final" and a.report["verdict"] == "rtl_bug"


def test_JSON_문자열_안의_중괄호는_문제없다():
    """find/replace 같은 Verilog 코드에 `{}`가 있어도 JSON 파싱이 깨지지 않는다."""
    obj = {"action": "tool", "tool": "propose_fix",
           "args": {"file": "rtl/a.v", "find": "x <= {a, b};", "replace": "x <= {b, a};"}}
    assert parse_action("text " + json.dumps(obj)).args["find"] == "x <= {a, b};"


@pytest.mark.parametrize("text,word", [
    ("", "비어"),
    ("그냥 말로 답함", "찾지 못"),
    ('{"thought":"x"}', "찾지 못"),                               # action 키가 없는 객체
    ('{"action":"dance"}', "알 수 없는 action"),
    ('{"action":"tool"}', "도구 이름"),
    ('{"action":"tool","tool":"t","args":[1]}', "객체"),
    ('{"action":"final","report":"done"}', "객체"),
    ('{"action":"tool","tool":"a"} {"action":"tool","tool":"b"}', "여러 개"),
])
def test_형식_오류는_설명이_있는_ProtocolError(text, word):
    """형식이 틀리면 LLM에게 되돌려줄 이유 문장이 들어 있는 예외가 난다."""
    with pytest.raises(ProtocolError) as e:
        parse_action(text)
    assert word in str(e.value)


# ---------------------------------------------------------------------------------------------
# validate_report
# ---------------------------------------------------------------------------------------------
def test_정상_보고서는_통과():
    """모든 필수 항목이 있고 근거 단계가 실제로 수행한 범위 안이면 문제 없음."""
    assert validate_report(good_report(), RTL_FILES, n_steps_done=3) == []


def test_unknown은_위치와_근거_없이도_통과():
    """증거가 부족하면 unknown으로 보고할 수 있다. 근거를 억지로 요구하면 오히려 지어내게 된다."""
    r = {"verdict": "unknown", "summary": "s", "root_cause": "need VCD", "confidence": "low"}
    assert validate_report(r, RTL_FILES, 2) == []


def test_rtl_bug인데_위치가_없거나_RTL이_아니면_거부():
    """rtl_bug는 RTL 논리 이름과 1 이상의 줄 번호가 필요하다 (TB 파일이나 지어낸 이름 거부)."""
    assert any("location" in p for p in validate_report(good_report(location=None), RTL_FILES))
    assert any("RTL 논리 이름" in p for p in validate_report(good_report(location={"file": "tb/x.v", "line": 3}), RTL_FILES))
    assert any("line" in p for p in validate_report(good_report(location={"file": "rtl/a.v", "line": 0}), RTL_FILES))
    assert any("line" in p for p in validate_report(good_report(location={"file": "rtl/a.v", "line": True}), RTL_FILES))


def test_근거가_없으면_rtl_bug와_tb_issue는_거부():
    """증거 없는 결론을 막는다."""
    assert any("evidence" in p for p in validate_report(good_report(evidence=[]), RTL_FILES))
    assert any("evidence" in p for p in validate_report(good_report(verdict="tb_issue", location=None, evidence=None), RTL_FILES))


def test_없는_단계를_인용하면_거부():
    """근거가 실제로 도구를 호출하지 않은 단계를 가리키면(지어낸 인용) 거부한다."""
    r = good_report(evidence=[{"step": 9, "observation": "o"}])
    assert any("step=9" in p for p in validate_report(r, RTL_FILES, n_steps_done=3))
    assert validate_report(r, RTL_FILES, n_steps_done=None) == []      # 단계 수를 모르면 구조만 본다


def test_valid_steps가_있으면_그_집합만_근거로_인정():
    """도구를 호출한 단계 집합을 주면, 범위 안이어도 그 집합에 없는 단계(형식 오류로 날린 단계)는 근거가 될 수 없다."""
    r = good_report(evidence=[{"step": 2, "observation": "o"}])
    assert validate_report(r, RTL_FILES, n_steps_done=3) == []                  # 범위만 보면 통과
    assert any("도구를 호출한 단계가 아니다" in p for p in validate_report(r, RTL_FILES, valid_steps={1, 3}))
    assert validate_report(r, RTL_FILES, valid_steps={2}) == []


@pytest.mark.parametrize("patch", [
    {"verdict": "maybe"}, {"confidence": "sure"}, {"summary": ""}, {"root_cause": "  "},
    {"fix_proposal_ids": "1"}, {"fix_proposal_ids": [1, "2"]},
    {"evidence": [{"step": "1", "observation": "o"}]}, {"evidence": [{"step": 1, "observation": ""}]},
])
def test_필드_형식_오류(patch):
    """각 필드의 타입과 값 범위를 확인한다."""
    assert validate_report(good_report(**patch), RTL_FILES, 3)


# ---------------------------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------------------------
LOG = ("noise\nCHECK_FAIL t=27 ns sig=count exp=3 got=4\nCHECK_FAIL t=37 ns sig=full exp=0 got=1\n"
       "CHECKS total=100 mismatches=2\n[TB] FAIL: 2 mismatches\n$finish called at time 400 ns\n")


@pytest.fixture
def ws():
    return DebugWorkspace({"rtl/a.v": "a\nb\n"}, {"tb/t.v": "x\n"}, LOG)


def make_ev(ws, **kw):
    return evidence_from_log("m", "FAIL", "FAIL", ws.log, ws.list_files(), **kw)


def test_초기_증거에_첫_실패와_요약이_들어간다(ws):
    """Agent가 첫 실패(시각, 신호, 기대/실제)와 체크 수, 파일 목록을 처음부터 본다."""
    msg = build_initial_message(make_ev(ws, spec_text="SPEC TEXT"))
    assert "t=27000 ps  sig=count  expected=3  got=4" in msg
    assert "total=100 mismatches=2" in msg
    assert "rtl/a.v (2" in msg and "testbench, read-only" in msg
    assert "SPEC TEXT" in msg and "VCD available: no" in msg


def test_초기_증거_실패_개수_상한과_표시(ws):
    """CHECK_FAIL이 많으면 앞 N개만 보여 주고 전체 개수를 알려 준다."""
    log = "\n".join(f"CHECK_FAIL t={i} ns sig=s exp=0 got=1" for i in range(1, 21))
    ev = evidence_from_log("m", "FAIL", "FAIL", log, ws.list_files(), max_fails=3)
    assert len(ev.check_fails) == 3 and ev.n_check_fails == 20
    assert "showing first 3 of 20" in build_initial_message(ev)


def test_CHECK_FAIL이_없으면_로그를_보라고_안내(ws):
    """파싱된 실패가 없으면(시간 단위 누락 등) 로그를 직접 보라는 문장이 들어간다."""
    ev = evidence_from_log("m", "FAIL", None, "Error: boom\n", ws.list_files())
    assert "get_log_snippet" in build_initial_message(ev)


def test_시스템_프롬프트에_도구와_규약이_들어간다(ws):
    """도구 명세에서 시그니처가 생성되고, TB 수정 금지와 근거 규칙이 명시된다."""
    p = build_system_prompt(tool_specs(ws))
    assert "read_rtl(file: string, start_line?: integer" in p
    assert "propose_fix(" in p and "tb_issue" in p
    assert "Never conclude from a value you have not seen" in p
    assert "read_vcd_signal" not in p                  # VCD 없는 작업공간에서는 안내하지 않음


def test_프롬프트는_결정적이고_대화를_누적한다(ws):
    """같은 입력은 같은 프롬프트(캐시 키 안정), 턴이 쌓이면 이전 단계가 모두 포함된다."""
    init = build_initial_message(make_ev(ws))
    t1 = Turn(1, '{"action":"tool","tool":"read_rtl"}', '{"lines":[]}')
    p1a, p1b = build_prompt(init, [t1], 5), build_prompt(init, [t1], 5)
    assert p1a == p1b
    t2 = Turn(2, '{"action":"tool","tool":"search_rtl"}', '{"matches":0}')
    p2 = build_prompt(init, [t1, t2], 4)
    assert "## Step 1" in p2 and "## Step 2" in p2 and "[4 step(s) left" in p2
    assert p2.index("## Step 1") < p2.index("## Step 2")


def test_긴_관측은_잘리고_표시된다():
    """도구 결과가 길어도 프롬프트에 들어가는 길이는 상한을 넘지 않는다."""
    big = "x" * 10_000
    out = render_turn(Turn(1, "{}", big))
    assert len(out) < 3300 and "관측 잘림" in out
    assert truncate_obs("short") == "short"


def test_프롬프트에_경로가_남지_않는다(tmp_path):
    """작업 공간에서 만든 초기 메시지 전체에 변형 ID나 실행 폴더가 새지 않는다 (정답 누출 방지)."""
    from core.debug_tools import workspace_from_files
    d = tmp_path / "B07" / "rtl"
    d.mkdir(parents=True)
    (d / "a.v").write_text("a\n")
    t = tmp_path / "t.v"
    t.write_text("x\n")
    w = workspace_from_files([d / "a.v"], [t], f'Error File "{d / "a.v"}" Line 1\nCHECK_FAIL t=1 ns sig=s exp=0 got=1\n')
    msg = build_initial_message(evidence_from_log("m", "FAIL", "FAIL", w.log, w.list_files()))
    assert "B07" not in msg and str(tmp_path) not in msg and "B07" not in w.log


_TOOLS = frozenset({"read_rtl", "propose_fix", "list_signals"})


def test_평탄한_도구_호출을_정규화한다():
    """v0c 형식 오류 5건은 모두 propose_fix 시도였고 4건이 `{"action":"propose_fix","file":...}`처럼 도구 이름을
    action 자리에 쓰고 인자를 최상위에 평탄하게 썼다. 의도가 분명하므로 tool 호출로 받아들이고 표시를 남긴다."""
    a = parse_action('{"thought":"t","action":"propose_fix","file":"rtl/a.v","find":"x","replace":"y","rationale":"r"}',
                     _TOOLS)
    assert (a.kind, a.tool, a.normalized) == ("tool", "propose_fix", True)
    assert a.args == {"file": "rtl/a.v", "find": "x", "replace": "y", "rationale": "r"} and a.thought == "t"


def test_평탄한_호출도_코드펜스와_args_객체를_받는다():
    """펜스 안(v0c B01)이거나 args를 따로 둔 경우도 같은 도구 호출이다. args가 있으면 그것을 쓴다."""
    a = parse_action('```json\n{"action":"read_rtl","file":"rtl/a.v"}\n```', _TOOLS)
    assert a.tool == "read_rtl" and a.args == {"file": "rtl/a.v"} and a.normalized
    b = parse_action('{"action":"read_rtl","args":{"file":"rtl/b.v"},"file":"rtl/a.v"}', _TOOLS)
    assert b.args == {"file": "rtl/b.v"}


def test_정규화는_tool_names가_있고_이름이_맞을_때만():
    """tool_names를 안 주면 기존대로 오류다. 모르는 이름이나 tool 필드가 다른 이름이면 오류를 유지한다."""
    txt = '{"action":"propose_fix","file":"rtl/a.v"}'
    with pytest.raises(ProtocolError, match="알 수 없는 action"):
        parse_action(txt)
    with pytest.raises(ProtocolError, match="알 수 없는 action"):
        parse_action('{"action":"dance","file":"x"}', _TOOLS)
    with pytest.raises(ProtocolError, match="알 수 없는 action"):
        parse_action('{"action":"propose_fix","tool":"read_rtl"}', _TOOLS)


def test_정상_호출은_정규화_표시가_없다():
    a = parse_action('{"action":"tool","tool":"read_rtl","args":{}}', _TOOLS)
    assert a.normalized is False
