"""Phase 7-1: Debug Agent 도구 (결정적, LLM/Vivado 불필요).

핵심 확인 사항
- 도구는 오류도 dict로 돌려준다 (예외로 루프를 죽이지 않는다).
- Agent는 논리 이름만 본다: 로그의 절대 경로(변형 ID 폴더 포함)가 모두 사라진다.
- propose_fix는 저장만 하고 파일을 쓰지 않으며, TB는 수정 대상이 아니다.
"""

import json

import pytest

from core.debug_tools import (MAX_LOG_LINES, MAX_PROPOSALS, MAX_SRC_LINES, DebugWorkspace, dispatch_debug,
                              sanitize_log, tool_specs, workspace_from_files)

RTL = "module m(input a, output y);\n  wire t;\n  assign t = a;\n  assign y = t;\nendmodule\n"
TB = "module tb;\n  reg a;\nendmodule\n"
LOG = "line1\nCHECK_FAIL t=27 ns sig=y exp=1 got=0\nline3\nCHECK_FAIL t=30 ns sig=y exp=0 got=1\n$finish called\n"


@pytest.fixture
def ws():
    return DebugWorkspace({"rtl/m.v": RTL}, {"tb/tb.v": TB}, LOG)


# ---------------------------------------------------------------------------------------------
# sanitize_log: 정답 단서가 될 수 있는 경로 제거
# ---------------------------------------------------------------------------------------------
def test_sanitize_경로의_변형ID_폴더가_사라진다():
    """로그에 `.../B07/rtl/fifo_ctrl.v`가 있으면 변형 ID(B07)가 Agent에게 새어 나간다. 논리 이름으로 바꿔야 한다."""
    log = r'Error: x File "C:\Users\a\runs\tbeval_llm_1\B07\rtl\fifo_ctrl.v" Line 5'
    out = sanitize_log(log, {"fifo_ctrl.v": "rtl/fifo_ctrl.v"})
    assert "B07" not in out and "tbeval" not in out
    assert 'File "rtl/fifo_ctrl.v" Line 5' in out


def test_sanitize_맵에_없는_파일은_basename만_남긴다():
    """알 수 없는 파일은 폴더를 숨기고 `<path>/이름`으로 표시한다."""
    out = sanitize_log("see /home/u/runs/B03/run/xsim.log now", {})
    assert "B03" not in out and "<path>/xsim.log" in out


def test_sanitize_posix_경로와_CRLF_모두_처리():
    """리눅스 경로와 CRLF 줄바꿈도 같은 규칙으로 처리한다."""
    out = sanitize_log("a /x/B01/rtl/m.v\r\nb\r\n", {"m.v": "rtl/m.v"})
    assert out == "a rtl/m.v\nb\n"


def test_workspace_from_files_논리이름과_로그정리(tmp_path):
    """실제 파일에서 만들면 이름이 rtl/·tb/ 접두사로 정해지고, 로그의 실제 경로가 논리 이름이 된다."""
    r = tmp_path / "B09" / "rtl"
    r.mkdir(parents=True)
    (r / "m.v").write_text(RTL)
    t = tmp_path / "tb.v"
    t.write_text(TB)
    log = f'Error File "{r / "m.v"}" Line 2'
    w = workspace_from_files([r / "m.v"], [t], log)
    assert set(w.rtl) == {"rtl/m.v"} and set(w.tb) == {"tb/tb.v"}
    assert "B09" not in w.log and 'File "rtl/m.v"' in w.log


def test_workspace_from_files_같은이름_두파일은_오류(tmp_path):
    """basename이 겹치면 논리 이름이 모호해지므로 조용히 덮어쓰지 않고 오류로 멈춘다."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "m.v").write_text(RTL)
    (tmp_path / "b" / "m.v").write_text(RTL)
    with pytest.raises(ValueError):
        workspace_from_files([tmp_path / "a" / "m.v", tmp_path / "b" / "m.v"], [], "")


# ---------------------------------------------------------------------------------------------
# get_log_snippet
# ---------------------------------------------------------------------------------------------
def test_로그_범위_조회(ws):
    """start_line부터 읽고, 남은 게 있으면 truncated와 next_start_line을 알려 준다."""
    r = ws.get_log_snippet(start_line=2, max_lines=2)
    assert [x["n"] for x in r["lines"]] == [2, 3]
    assert r["truncated"] and r["next_start_line"] == 4 and r["total_lines"] == 5


def test_로그_패턴_조회와_context(ws):
    """pattern은 일치하는 줄만, context를 주면 앞뒤 줄도 함께 보여 준다."""
    r = ws.get_log_snippet(pattern="CHECK_FAIL")
    assert r["matches"] == 2 and [x["n"] for x in r["lines"]] == [2, 4]
    r2 = ws.get_log_snippet(pattern="CHECK_FAIL", context=1)
    assert [x["n"] for x in r2["lines"]] == [1, 2, 3, 4, 5]


def test_로그_정규식_오류는_dict(ws):
    """잘못된 정규식은 예외가 아니라 error를 돌려준다."""
    assert "error" in ws.get_log_snippet(pattern="(")


def test_로그_범위_밖과_상한(ws):
    """범위를 넘으면 오류, 요청 줄 수는 상한(MAX_LOG_LINES)으로 줄인다."""
    assert "error" in ws.get_log_snippet(start_line=99)
    big = DebugWorkspace({}, {}, "\n".join(f"l{i}" for i in range(500)))
    assert big.get_log_snippet(max_lines=9999)["returned"] == MAX_LOG_LINES


def test_긴_줄은_잘라서_보여준다(ws):
    """한 줄이 아주 길어도 출력은 상한을 넘지 않는다 (VCD 한 줄 덤프 같은 경우)."""
    w = DebugWorkspace({}, {}, "x" * 5000)
    assert len(w.get_log_snippet()["lines"][0]["text"]) < 260


# ---------------------------------------------------------------------------------------------
# read_rtl / read_tb / search_rtl
# ---------------------------------------------------------------------------------------------
def test_read_rtl_줄번호와_범위(ws):
    """줄 번호는 1부터, end_line을 생략하면 파일 끝까지."""
    r = ws.read_rtl("rtl/m.v", 2, 3)
    assert [x["n"] for x in r["lines"]] == [2, 3] and "assign t = a;" in r["lines"][1]["text"]
    assert not r["truncated"]


def test_read_rtl_없는_파일은_후보를_알려준다(ws):
    """이름을 틀리면 사용 가능한 논리 이름을 알려 줘서 LLM이 스스로 고치게 한다."""
    r = ws.read_rtl("m.v")
    assert "error" in r and r["available"] == ["rtl/m.v"]


def test_read_rtl은_TB를_읽지_못한다(ws):
    """read_rtl로 TB 파일을 요청하면 실패한다 (역할 분리). TB는 read_tb로만 읽는다."""
    assert "error" in ws.read_rtl("tb/tb.v")
    assert ws.read_tb("tb/tb.v")["lines"][0]["text"] == "module tb;"


def test_긴_소스는_120줄로_자르고_이어읽기_위치(ws):
    """한 번에 MAX_SRC_LINES줄까지만 준다."""
    w = DebugWorkspace({"rtl/big.v": "\n".join(f"x{i}" for i in range(300))}, {}, "")
    r = w.read_rtl("rtl/big.v")
    assert r["start_line"] == 1 and r["end_line"] == MAX_SRC_LINES and len(r["lines"]) == MAX_SRC_LINES
    assert r["truncated"] and r["next_start_line"] == MAX_SRC_LINES + 1


def test_search_rtl(ws):
    """신호가 대입되는 줄을 파일과 줄 번호로 찾는다."""
    r = ws.search_rtl(r"assign\s+t\b")
    assert r["matches"] == 1 and r["results"][0] == {"file": "rtl/m.v", "n": 3, "text": "  assign t = a;"}
    assert "error" in ws.search_rtl("(")


# ---------------------------------------------------------------------------------------------
# propose_fix
# ---------------------------------------------------------------------------------------------
def test_propose_fix_diff와_줄번호(ws):
    """수정안은 diff와 변경 줄 번호를 돌려주고 id로 저장된다. 원본 텍스트는 바뀌지 않는다."""
    r = ws.propose_fix("rtl/m.v", "assign y = t;", "assign y = ~t;", "inverted")
    assert r["proposal_id"] == 1 and r["line"] == 4
    assert "-  assign y = t;" in r["diff"] and "+  assign y = ~t;" in r["diff"]
    assert "assign y = t;" in ws.rtl["rtl/m.v"]                  # 적용되지 않음
    assert ws.proposals[0].rationale == "inverted"


def test_propose_fix_TB는_거부(ws):
    """TB를 고쳐서 통과시키는 행동을 막는다. 대신 tb_issue 보고를 안내한다."""
    r = ws.propose_fix("tb/tb.v", "reg a;", "reg a = 1;")
    assert "error" in r and "tb_issue" in r["error"]
    assert ws.proposals == []


@pytest.mark.parametrize("find,replace,word", [
    ("", "x", "비어"), ("a", "a", "같음"), ("nope", "x", "없음"), ("t", "q", "번 나타남")])
def test_propose_fix_잘못된_find(ws, find, replace, word):
    """find가 비었거나, replace와 같거나, 없거나, 여러 번 나오면 오류와 이유를 돌려준다."""
    r = ws.propose_fix("rtl/m.v", find, replace)
    assert word in r["error"] and ws.proposals == []


def test_propose_fix_중복과_상한(ws):
    """같은 제안은 새로 만들지 않고 기존 id를 돌려주며, 제안 수에는 상한이 있다."""
    a = ws.propose_fix("rtl/m.v", "assign y = t;", "assign y = ~t;")
    b = ws.propose_fix("rtl/m.v", "assign y = t;", "assign y = ~t;")
    assert b["proposal_id"] == a["proposal_id"] and b["duplicate"] and len(ws.proposals) == 1
    w = DebugWorkspace({"rtl/m.v": "\n".join(f"l{i}" for i in range(20))}, {}, "")
    for i in range(MAX_PROPOSALS):
        assert "proposal_id" in w.propose_fix("rtl/m.v", f"l{i}\n", f"L{i}\n")
    assert "error" in w.propose_fix("rtl/m.v", "l10\n", "Z\n")


def test_propose_fix_CRLF_파일도_일치(ws):
    """Windows(CRLF) 소스도 읽을 때 LF로 통일하므로 LLM이 보낸 LF 기준 find가 일치한다."""
    w = DebugWorkspace({"rtl/m.v": "a\r\nb\r\n"}, {}, "")
    assert w.propose_fix("rtl/m.v", "a\nb", "a\nc")["proposal_id"] == 1


_CTRL = """module c;
  case (x)
    2'b11: begin
      if (!empty && !full) begin
        wr_ptr <= wr_ptr + 1;
        rd_ptr <= rd_ptr;
      end
      else if (empty) begin
        wr_ptr <= wr_ptr + 1;
      end
    end
  endcase
endmodule
"""


def test_propose_fix_줄번호는_find_첫줄이_아니라_첫_변경_줄():
    """v0c B03: find가 `if` 줄(4)부터 시작하지만 바뀌는 줄은 `rd_ptr <= rd_ptr;`(6)다. Agent가 도구가 돌려준
    line을 보고서 위치로 베껴서 near로 채점됐다. line은 처음 달라지는 줄이어야 한다."""
    w = DebugWorkspace({"rtl/c.v": _CTRL}, {}, "")
    find = "      if (!empty && !full) begin\n        wr_ptr <= wr_ptr + 1;\n        rd_ptr <= rd_ptr;\n      end"
    r = w.propose_fix("rtl/c.v", find, find.replace("rd_ptr <= rd_ptr;", "rd_ptr <= rd_ptr + 1;"))
    assert r["line"] == 6 and w.proposals[0].line == 6


def test_propose_fix_줄을_끼워넣으면_삽입_위치():
    """v0c B15: 블록 중간에 줄을 추가하면 처음 달라지는 줄은 삽입 위치다 (find 첫 줄이 아니다)."""
    w = DebugWorkspace({"rtl/c.v": _CTRL}, {}, "")
    find = "      if (!empty && !full) begin\n        wr_ptr <= wr_ptr + 1;\n        rd_ptr <= rd_ptr;\n      end"
    rep = "      if (!empty && !full) begin\n        wr_ptr <= wr_ptr + 1;\n        rd_ptr <= rd_ptr;\n        cnt <= cnt;\n      end"
    assert w.propose_fix("rtl/c.v", find, rep)["line"] == 7


def test_propose_fix_줄_중간에서_시작하는_find():
    """find가 줄 중간에서 시작해도 변경 문자가 있는 줄 번호를 돌려준다."""
    w = DebugWorkspace({"rtl/c.v": "a\nassign y = t & u;\nz\n"}, {}, "")
    assert w.propose_fix("rtl/c.v", "t & u", "t | u")["line"] == 2


def test_propose_fix_중복_제안도_같은_줄():
    """같은 수정안을 다시 내면 저장된 제안의 (변경) 줄을 그대로 돌려준다."""
    w = DebugWorkspace({"rtl/c.v": _CTRL}, {}, "")
    find = "        wr_ptr <= wr_ptr + 1;\n        rd_ptr <= rd_ptr;"
    rep = "        wr_ptr <= wr_ptr + 1;\n        rd_ptr <= rd_ptr + 1;"
    a = w.propose_fix("rtl/c.v", find, rep)
    b = w.propose_fix("rtl/c.v", find, rep)
    assert a["line"] == b["line"] == 6 and b["duplicate"] is True


# ---------------------------------------------------------------------------------------------
# dispatch / 명세
# ---------------------------------------------------------------------------------------------
def test_dispatch_문자열_숫자를_고쳐서_실행(ws):
    """LLM이 `"2"`처럼 문자열로 숫자를 주어도 정수로 바꿔 실행한다."""
    r = dispatch_debug(ws, "read_rtl", {"file": "rtl/m.v", "start_line": "2", "end_line": "3"})
    assert [x["n"] for x in r["lines"]] == [2, 3]


def test_dispatch_오류는_모두_dict(ws):
    """모르는 도구, 필수 인자 누락, 모르는 인자 모두 예외가 아니라 error다."""
    assert "available" in dispatch_debug(ws, "rm_rf", {})
    assert "필수" in dispatch_debug(ws, "read_rtl", {})["error"]
    assert "allowed" in dispatch_debug(ws, "read_rtl", {"file": "rtl/m.v", "bogus": 1})
    assert "error" in dispatch_debug(ws, "read_rtl", {"file": "rtl/m.v", "start_line": "abc"})
    assert dispatch_debug(ws, "get_log_snippet", None)["total_lines"] == 5     # args가 None이어도 죽지 않음


def test_VCD가_없으면_VCD_도구는_명세와_실행_모두에서_빠진다(ws):
    """VCD가 없는 실행(컴파일 실패 등)에서 Agent가 없는 도구를 부르지 않게 명세에서 뺀다."""
    names = {s["name"] for s in tool_specs(ws)}
    assert "read_vcd_signal" not in names and "read_rtl" in names
    assert "available" in dispatch_debug(ws, "read_vcd_signal", {"name": "x"})


def test_명세는_JSON_직렬화_가능하고_이름이_중복되지_않는다(ws):
    """프롬프트에 넣을 명세가 올바른 JSON이고 이름이 겹치지 않는다."""
    specs = tool_specs(ws)
    json.dumps(specs)
    assert len({s["name"] for s in specs}) == len(specs)


def test_VCD_도구는_VcdTools로_위임된다():
    """VCD 도구 이름은 기존 `VcdTools` 디스패처로 간다 (이미 검증된 코드를 재사용)."""
    calls = []

    class FakeVcd:
        def list_signals(self, pattern=None, limit=50):
            calls.append((pattern, limit))
            return {"total": 0, "signals": []}

    w = DebugWorkspace({}, {}, "", vcd=FakeVcd())
    r = dispatch_debug(w, "list_signals", {"pattern": "ptr", "limit": "5"})
    assert r["total"] == 0 and calls == [("ptr", 5)]


def test_끝_줄바꿈이_가짜_마지막_줄을_만들지_않는다():
    """파일이 줄바꿈으로 끝나도 줄 수가 늘지 않고, 존재하지 않는 줄은 읽히지 않는다 (LLM이 없는 줄 번호를 인용하지 않게)."""
    w = DebugWorkspace({"rtl/a.v": "a\nb\n"}, {"tb/t.v": "x\n"}, "l1\nl2\n")
    fl = w.list_files()
    assert fl["rtl"][0]["lines"] == 2 and fl["tb"][0]["lines"] == 1 and fl["log_lines"] == 2
    r = w.read_rtl("rtl/a.v")
    assert r["total_lines"] == 2 and [x["n"] for x in r["lines"]] == [1, 2]
    assert "error" in w.read_rtl("rtl/a.v", start_line=3)
    assert "error" in w.get_log_snippet(start_line=3)


# ---------------------------------------------------------------------------------------------
# 7-4 1차 실측에서 발견된 결함의 회귀 테스트
# ---------------------------------------------------------------------------------------------
def test_로그의_시각과_경과시간은_정규화된다():
    """xsim 로그의 `Start of session at: ...`, `Exiting xsim at ...`, `Time (s): cpu = ...`는 실행마다 달라서
    프롬프트가 매번 바뀌고 디스크 캐시가 맞지 않았다 (실측 1차에서 같은 변형을 다시 돌려도 캐시 0회). 지운다."""
    a = ("  **** Start of session at: Tue Nov 24 18:22:41 2026\nCHECK_FAIL t=1 ns sig=y exp=0 got=1\n"
         "INFO: [Common 17-206] Exiting xsim at Tue Nov 24 18:22:43 2026...\nTime (s): cpu = 00:00:01 ; elapsed = 00:00:03\n")
    b = a.replace("18:22:41", "09:01:07").replace("18:22:43", "09:01:12").replace("Tue Nov 24", "Wed Dec  2") \
         .replace("cpu = 00:00:01 ; elapsed = 00:00:03", "cpu = 00:00:09 ; elapsed = 00:00:20")
    assert a != b and sanitize_log(a, {}) == sanitize_log(b, {})
    out = sanitize_log(a, {})
    assert "2026" not in out and "<time>" in out and "CHECK_FAIL t=1 ns" in out


def test_시각_정규화가_실패_정보를_건드리지_않는다():
    """시각처럼 보이지 않는 숫자(시뮬레이션 시각 41010 ns, 줄 번호)와 상대 경로(`tb/x.v`)는 그대로 남는다."""
    s = '$finish called at time : 41010 ns : File "tb/x.v" Line 204'
    assert sanitize_log(s, {"x.v": "tb/x.v"}) == s


def test_상대경로의_슬래시를_절대경로로_오인하지_않는다():
    """`tb/x.v`의 `/x.v`를 절대 경로로 보고 `tbtb/x.v`로 바꾸는 결함을 막는다. 절대 경로는 여전히 논리 이름이 된다."""
    m = {"x.v": "tb/x.v"}
    assert sanitize_log('File "tb/x.v" Line 3', m) == 'File "tb/x.v" Line 3'
    assert sanitize_log('see rtl/a.v and /abs/B07/x.v and C:\\w\\B07\\x.v', m) == 'see rtl/a.v and tb/x.v and tb/x.v'


def test_시각만_다른_두_로그는_같은_초기_프롬프트를_만든다():
    """정규화의 목적: 같은 실패는 같은 프롬프트(캐시 키)가 된다."""
    from core.debug_protocol import build_initial_message, evidence_from_log
    base = "Start of session at: Tue Nov 24 18:22:41 2026\nCHECK_FAIL t=1 ns sig=y exp=0 got=1\n"
    msgs = []
    for stamp in ("18:22:41", "03:15:59"):
        w = DebugWorkspace({"rtl/a.v": "x\n"}, {}, sanitize_log(base.replace("18:22:41", stamp), {}))
        msgs.append(build_msg(w, build_initial_message, evidence_from_log))
    assert msgs[0] == msgs[1]


def build_msg(w, build_initial_message, evidence_from_log):
    return build_initial_message(evidence_from_log("m", "FAIL", "FAIL", w.log, w.list_files()))


@pytest.mark.parametrize("find,replace", [
    ("assign y = t;", "assign y = t; // 주석만 추가"),
    ("assign y = t;", "assign y = t;   "),
    ("assign y = t;", "assign   y   =   t ;"),
    ("assign y = t;", "assign y = t; /* block */"),
])
def test_주석이나_공백만_바꾸는_수정안은_거부(ws, find, replace):
    """실측 1차에서 Agent가 `// count remains unchanged` 주석만 추가하는 수정안을 냈고 시스템이 받아들였다.
    동작이 달라지지 않는 수정안은 증거가 아니므로 거부하고 저장하지 않는다."""
    r = ws.propose_fix("rtl/m.v", find, replace)
    assert "주석이나 공백" in r["error"] and ws.proposals == []


def test_주석과_함께_실제_코드도_바꾸면_수락(ws):
    """주석을 같이 바꿔도 코드가 달라지면 정상 수정안이다."""
    r = ws.propose_fix("rtl/m.v", "assign y = t;", "assign y = ~t; // fixed")
    assert r["proposal_id"] == 1


def test_propose_fix_설명에_원본_기준과_거부_조건이_있다(ws):
    """Agent가 이전 제안이 적용된 줄 알고 그 위에 find를 쓰는 실수(실측 1차 B12)를 설명으로 막는다."""
    d = next(s for s in tool_specs(ws) if s["name"] == "propose_fix")["description"]
    assert "원본" in d and "누적되지 않음" in d and "주석이나 공백" in d