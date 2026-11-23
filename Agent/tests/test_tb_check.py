"""TB Generator 6-2: LLM 응답에서 코드 추출, TB 정적 검사기.

작은 카운터 DUT(ck, 비동기 active-high reset, en, count[3:0])를 기준으로 "정상 TB" 하나를 만들고,
거기서 한 군데씩만 망가뜨려 검사기가 그 문제를 정확한 코드로 잡는지 본다.
실제 사람 TB(dut/sync_fifo/tb)로도 검사기가 현실과 맞는지 확인한다 (파일이 없으면 건너뜀).
"""

from pathlib import Path

import pytest

from core.rtl_summary import summarize_rtl
from core.tb_check import Issue, check_tb, errors_of, extract_verilog, has_errors

ROOT = Path(__file__).resolve().parents[1]

DUT = """\
module counter(input ck, input reset, input en, output reg [3:0] count);
  always @(posedge ck or posedge reset)
    if (reset) count <= 0; else if (en) count <= count + 1;
endmodule
"""

INST = "counter dut (.ck(ck), .reset(reset), .en(en), .count(count));"
CHECK_BLOCK = """\
  always @(posedge ck) begin
    #2;
    checks = checks + 1;
    if (count !== m) begin
      errors = errors + 1;
      if (errors <= 10) $display("CHECK_FAIL t=%0t sig=count exp=%0h got=%0h", $time, m, count);
    end
  end
"""
GOOD_TB = f"""\
module tb_counter;
  reg ck, reset, en;
  wire [3:0] count;
  {INST}
  always #5 ck = ~ck;
  reg [3:0] m;
  integer checks, errors, seed, i;
  initial begin #100000; $display("[TB] FAIL: timeout"); $finish; end
  always @(posedge ck or posedge reset) if (reset) m <= 0; else if (en) m <= m + 1;
{CHECK_BLOCK}
  initial begin
    ck = 0; reset = 0; en = 0; checks = 0; errors = 0; seed = 1;
    @(negedge ck) reset = 1;
    @(negedge ck) reset = 0;
    for (i = 0; i < 100; i = i + 1) begin
      @(negedge ck) en = $random(seed);
    end
    $display("CHECKS total=%0d mismatches=%0d", checks, errors);
    if (errors == 0) $display("[TB] PASS");
    else $display("[TB] FAIL: %0d mismatches", errors);
    $finish;
  end
endmodule
"""


@pytest.fixture
def summary(tmp_path):
    """timescale이 없는 카운터 DUT의 요약."""
    f = tmp_path / "counter.v"
    f.write_text(DUT)
    return summarize_rtl([f], top="counter")


@pytest.fixture
def summary_ts(tmp_path):
    """RTL 전체에 `timescale 1ns/1ps가 있는 카운터 DUT의 요약."""
    f = tmp_path / "counter.v"
    f.write_text("`timescale 1ns/1ps\n" + DUT)
    return summarize_rtl([f], top="counter")


def codes(issues, level=None):
    return {i.code for i in issues if level is None or i.level == level}


# ------------------------------------------------------------ 코드 추출
def test_extract_takes_fenced_block_and_ignores_prose():
    """코드 펜스 안의 코드만 꺼내고, 펜스 밖 설명은 버린다."""
    code, probs = extract_verilog("설명입니다\n```verilog\nmodule a;\nendmodule\n```\n끝")
    assert code == "module a;\nendmodule\n"
    assert probs == []


def test_extract_picks_longest_module_block_and_reports_multiple():
    """module을 포함한 블록이 여럿이면 가장 긴 것을 쓰고 그 사실을 알린다."""
    text = "```verilog\nmodule a;\nendmodule\n```\n```verilog\nmodule bbbb;\n reg x;\nendmodule\n```"
    code, probs = extract_verilog(text)
    assert "bbbb" in code
    assert any("2개" in p for p in probs)


def test_extract_ignores_blocks_without_module():
    """module이 없는 블록(예: 실행 방법 설명)은 후보에서 제외한다."""
    text = "```bash\niverilog a.v\n```\n```verilog\nmodule a;\nendmodule\n```"
    code, _ = extract_verilog(text)
    assert code.startswith("module a;")


def test_extract_without_fence_uses_first_module_to_last_endmodule():
    """펜스 없이 답해도 module~endmodule을 꺼내되, 펜스가 없었다고 알린다."""
    code, probs = extract_verilog("Here you go:\nmodule a;\nendmodule\nThanks!")
    assert code == "module a;\nendmodule\n"
    assert any("펜스" in p for p in probs)


def test_extract_without_fence_keeps_timescale_line_before_module():
    """펜스 없는 응답에서 module 바로 앞의 `timescale 줄은 코드에 포함한다."""
    code, _ = extract_verilog("`timescale 1ns/1ps\nmodule a;\nendmodule")
    assert code.startswith("`timescale 1ns/1ps")


def test_extract_truncated_fence_returns_empty():
    """닫는 펜스와 endmodule이 없는 (잘린) 응답은 코드를 돌려주지 않는다."""
    code, probs = extract_verilog("```verilog\nmodule a;\n  reg x;\n")
    assert code == ""
    assert probs


# ------------------------------------------------------------ 정상 TB
def test_good_tb_has_no_errors(summary):
    """규약을 다 지킨 TB는 error가 없다."""
    assert not has_errors(check_tb(GOOD_TB, summary))


def test_good_tb_has_no_warnings_either(summary):
    """기준 TB는 경고도 없다 (이후 테스트가 '이 경고는 이 변경 때문'이라고 말할 수 있게)."""
    assert check_tb(GOOD_TB, summary) == []


def test_empty_code_is_an_error(summary):
    """빈 코드는 no_code 에러."""
    assert codes(check_tb("  \n", summary)) == {"no_code"}


def test_issue_str_shows_level_code_and_message():
    """Issue는 사람이 읽을 수 있는 한 줄로 출력된다."""
    assert str(Issue("error", "x", "msg")) == "[error] x: msg"


def test_errors_of_filters_by_level(summary):
    """errors_of는 error만 돌려준다."""
    iss = [Issue("error", "a", ""), Issue("warning", "b", "")]
    assert [i.code for i in errors_of(iss)] == ["a"]


# ------------------------------------------------------------ 모듈 구조
def test_tb_with_ports_is_rejected(summary):
    """최상위 TB는 포트가 없어야 한다."""
    tb = GOOD_TB.replace("module tb_counter;", "module tb_counter(input x);")
    assert "tb_has_ports" in codes(check_tb(tb, summary), "error")


def test_tb_name_equal_to_dut_is_rejected(summary):
    """TB 모듈 이름이 DUT와 같으면 계층이 꼬인다."""
    tb = GOOD_TB.replace("module tb_counter;", "module counter;")
    assert "tb_name_clash" in codes(check_tb(tb, summary), "error")


def test_two_modules_in_one_file_are_rejected(summary):
    """TB 파일에 모듈이 둘 이상이면 거부한다 (보조 모듈은 허용하지 않음)."""
    assert "multiple_modules" in codes(check_tb(GOOD_TB + "module helper; endmodule\n", summary), "error")


def test_missing_endmodule_is_flagged_as_truncated(summary):
    """endmodule이 모자라면 출력이 잘린 것으로 본다."""
    assert "unbalanced_module" in codes(check_tb(GOOD_TB.replace("endmodule", ""), summary), "error")


def test_systemverilog_constructs_are_rejected(summary):
    """v1은 Verilog만: logic, $urandom 같은 SV 구문이 있으면 거부한다."""
    tb = GOOD_TB.replace("reg [3:0] m;", "logic [3:0] m;").replace("$random(seed)", "$urandom")
    assert "systemverilog_construct" in codes(check_tb(tb, summary), "error")


def test_keyword_inside_string_is_not_systemverilog(summary):
    """문자열 안의 'int', 'logic' 같은 단어는 키워드로 보지 않는다."""
    tb = GOOD_TB.replace('"CHECKS total', '"int logic bit CHECKS total')
    assert "systemverilog_construct" not in codes(check_tb(tb, summary))


def test_comments_are_ignored(summary):
    """주석 안의 $stop이나 `timescale 은 검사 대상이 아니다."""
    tb = GOOD_TB.replace("  always #5", "  // $stop `timescale 1ns/1ps logic\n  always #5")
    assert not has_errors(check_tb(tb, summary))


# ------------------------------------------------------------ timescale
def test_timescale_forbidden_when_rtl_has_none(summary):
    """RTL에 timescale이 없는데 TB에 쓰면 xelab이 XSIM 43-4099로 실패하므로 에러다."""
    assert "timescale_forbidden" in codes(check_tb("`timescale 1ns/1ps\n" + GOOD_TB, summary), "error")


def test_timescale_required_when_rtl_has_it(summary_ts):
    """RTL 전체에 timescale이 있으면 TB에도 있어야 한다."""
    assert "timescale_missing" in codes(check_tb(GOOD_TB, summary_ts), "error")


def test_timescale_must_match_rtl_value(summary_ts):
    """TB의 timescale 값이 RTL과 다르면 에러다."""
    assert "timescale_mismatch" in codes(check_tb("`timescale 1ns/1ns\n" + GOOD_TB, summary_ts), "error")


def test_matching_timescale_passes_even_with_different_spacing(summary_ts):
    """공백 표기만 다른 같은 값(1ns / 1ps)은 통과한다."""
    assert not has_errors(check_tb("`timescale 1ns / 1ps\n" + GOOD_TB, summary_ts))


# ------------------------------------------------------------ DUT 인스턴스와 포트
def test_dut_must_be_instantiated(summary):
    """DUT를 인스턴스화하지 않은 TB는 에러다."""
    assert "dut_not_instantiated" in codes(check_tb(GOOD_TB.replace(INST, ""), summary), "error")


def test_positional_connection_is_rejected(summary):
    """위치 기반 연결은 포트 순서 실수를 못 잡으므로 거부한다."""
    tb = GOOD_TB.replace(INST, "counter dut (ck, reset, en, count);")
    assert "dut_positional_ports" in codes(check_tb(tb, summary), "error")


def test_missing_port_connection_is_reported(summary):
    """연결이 빠진 포트가 있으면 에러다."""
    tb = GOOD_TB.replace(" .en(en),", "")
    iss = check_tb(tb, summary)
    assert "dut_port_missing" in codes(iss, "error")
    assert "['en']" in next(i.message for i in iss if i.code == "dut_port_missing")


def test_unknown_port_connection_is_reported(summary):
    """DUT에 없는 포트(LLM이 지어낸 포트)를 연결하면 에러다."""
    tb = GOOD_TB.replace(".en(en),", ".en(en), .valid(en),")
    assert "dut_port_unknown" in codes(check_tb(tb, summary), "error")


def test_connection_with_nested_parentheses_is_parsed(summary):
    """연결식 안에 괄호가 있어도 포트 목록을 올바르게 읽는다."""
    tb = GOOD_TB.replace(".count(count)", ".count(count[3:0])")
    assert not has_errors(check_tb(tb, summary))


# ------------------------------------------------------------ 입력 구동 / 출력 관찰
def test_undriven_input_is_an_error(summary):
    """입력에 연결된 TB 신호를 아무도 구동하지 않으면 X로 도는 TB라서 에러다."""
    tb = GOOD_TB.replace("@(negedge ck) en = $random(seed);", "@(negedge ck) i = $random(seed);").replace("en = 0;", "")
    iss = check_tb(tb, summary)
    assert "input_undriven" in codes(iss, "error")
    assert "'en'" in next(i.message for i in iss if i.code == "input_undriven")


def test_bit_select_assignment_counts_as_driving(summary):
    """`en[0] = ...`처럼 비트 선택 대입도 구동으로 인정한다."""
    tb = GOOD_TB.replace("@(negedge ck) en = $random(seed);", "@(negedge ck) en[0] = $random(seed);")
    assert "input_undriven" not in codes(check_tb(tb, summary))


def test_unobserved_output_is_a_warning(summary):
    """출력 신호를 선언 외에 어디서도 안 쓰면 경고 (검증이 안 되는 출력)."""
    tb = GOOD_TB.replace(CHECK_BLOCK, "  always @(posedge ck) begin #2; checks = checks + 1; end\n")
    assert "output_unobserved" in codes(check_tb(tb, summary), "warning")


def test_no_case_equality_is_a_warning(summary):
    """`!==` 없이 `!=`만 쓰면 X가 통과될 수 있어 경고한다."""
    assert "no_case_equality" in codes(check_tb(GOOD_TB.replace("!==", "!="), summary), "warning")


# ------------------------------------------------------------ 판정 마커와 종료
def test_missing_pass_marker_is_an_error(summary):
    """[TB] PASS가 없으면 Phase 2 판정이 PASS를 인정하지 않으므로 에러다."""
    tb = GOOD_TB.replace('$display("[TB] PASS")', '$display("all good")')
    assert "no_pass_marker" in codes(check_tb(tb, summary), "error")


def test_missing_fail_marker_is_an_error(summary):
    """[TB] FAIL이 없으면 변형 DUT를 잡아도 FAIL로 판정되지 않는다."""
    tb = GOOD_TB.replace('$display("[TB] FAIL: %0d mismatches", errors)', '$display("bad")') \
                .replace('$display("[TB] FAIL: timeout")', '$display("timeout")')
    assert "no_fail_marker" in codes(check_tb(tb, summary), "error")


def test_pass_marker_with_trailing_text_is_rejected(summary):
    """PASS 줄에 다른 글자가 붙으면 파서 규약(줄 전체가 [TB] PASS)과 달라 에러다."""
    tb = GOOD_TB.replace('"[TB] PASS"', '"[TB] PASS all checks"')
    assert {"no_pass_marker", "bad_tb_marker"} <= codes(check_tb(tb, summary), "error")


def test_tb_prefix_used_for_progress_message_is_rejected(summary):
    """[TB] 접두는 판정 전용이다. 진행 메시지에 쓰면 에러."""
    tb = GOOD_TB.replace("    ck = 0;", '    $display("[TB] start");\n    ck = 0;')
    assert "bad_tb_marker" in codes(check_tb(tb, summary), "error")


def test_missing_finish_is_an_error(summary):
    """$finish가 없으면 xsim이 끝나지 않을 수 있다."""
    assert "no_finish" in codes(check_tb(GOOD_TB.replace("$finish;", ""), summary), "error")


@pytest.mark.parametrize("task,code", [("$stop;", "uses_stop"), ('$fatal(1, "x");', "uses_error_task"),
                                       ('$error("x");', "uses_error_task"),
                                       ('$dumpfile("a.vcd");', "uses_dump")])
def test_forbidden_system_tasks(summary, task, code):
    """$stop/$fatal/$error/$dumpfile은 금지: 판정이 섞이거나, VCD를 Agent의 Tcl이 따로 만들기 때문이다."""
    tb = GOOD_TB.replace("    ck = 0;", f"    {task}\n    ck = 0;")
    assert code in codes(check_tb(tb, summary), "error")


def test_missing_watchdog_is_a_warning(summary):
    """워치독이 없으면 경고 (규약이지만 TB 오류는 아님)."""
    tb = GOOD_TB.replace('  initial begin #100000; $display("[TB] FAIL: timeout"); $finish; end\n', "")
    assert "no_watchdog" in codes(check_tb(tb, summary), "warning")


def test_missing_optional_logs_are_warnings(summary):
    """CHECK_FAIL, CHECKS, 랜덤 자극이 없어도 평가는 되므로 경고만 낸다."""
    tb = GOOD_TB.replace('"CHECK_FAIL', '"cf').replace('"CHECKS total', '"cs total').replace("$random(seed)", "1")
    iss = check_tb(tb, summary)
    assert {"no_check_fail_log", "no_checks_summary", "no_random"} <= codes(iss, "warning")
    assert not has_errors(iss)


# ------------------------------------------------------------ 실제 파일로 현실 확인
@pytest.fixture
def real_summary():
    d = ROOT / "dut" / "sync_fifo"
    if not (d / "rtl").is_dir():
        pytest.skip("dut/sync_fifo가 없음")
    return summarize_rtl(sorted((d / "rtl").glob("*.v")), top="sync_fifo")


def test_human_self_checking_tb_passes_the_checker(real_summary):
    """Phase 4에서 직접 쓴 self-checking TB는 error 없이 통과한다 (검사기가 현실과 어긋나지 않는다는 근거)."""
    code = (ROOT / "dut/sync_fifo/tb/tb_sync_fifo_sc.v").read_text(encoding="utf-8")
    assert not has_errors(check_tb(code, real_summary))


def test_original_non_self_checking_tb_is_rejected(real_summary):
    """원래의 눈으로 보는 TB는 [TB] 마커가 없고 timescale이 RTL과 충돌하므로 검사기가 거부한다."""
    code = (ROOT / "dut/sync_fifo/tb/tb_sync_fifo_ref.v").read_text(encoding="utf-8")
    assert {"no_pass_marker", "no_fail_marker", "timescale_forbidden"} <= codes(check_tb(code, real_summary), "error")
