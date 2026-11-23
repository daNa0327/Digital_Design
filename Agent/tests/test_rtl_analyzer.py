"""RTL Analyzer 5-1: 주석 제거, 모듈/포트/파라미터 추출."""

from pathlib import Path

import pytest

from core.rtl_analyzer import strip_comments, parse_modules, parse_files, eval_const

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "dut" / "sync_fifo" / "rtl"


def port(mod, name):
    return next(p for p in mod.ports if p.name == name)


# ------------------------------------------------------------ strip_comments
def test_strip_comments_keeps_length_and_lines():
    """주석을 지워도 문자 수와 줄 수가 그대로여야 한다 (그래야 포트의 줄 번호가 원본과 일치)."""
    src = "a // x\n/* b\nc */ d\n"
    out = strip_comments(src)
    assert len(out) == len(src)
    assert out.count("\n") == src.count("\n")
    assert "x" not in out and "b" not in out.replace("\n", "")
    assert out.split("\n")[2].strip().endswith("d")


def test_strip_comments_ignores_slashes_in_string():
    """문자열 안의 // 와 /* 는 주석이 아니므로 그대로 둔다."""
    src = 'initial $display("a // b /* c");\n'
    assert strip_comments(src) == src


# ------------------------------------------------------------ eval_const
@pytest.mark.parametrize("expr,env,exp", [
    ("8", {}, 8), ("W-1", {"W": 8}, 7), ("(A+1)*2", {"A": 3}, 8),
    ("$clog2(DEPTH)", {"DEPTH": 8}, 3), ("$clog2(9)", {}, 4),
    ("1<<4", {}, 16), ("X-1", {}, None), ("a ? b : c", {}, None),
])
def test_eval_const(expr, env, exp):
    """정수 식 계산기: 사칙, 시프트, $clog2, 파라미터 대입은 계산하고 모르는 이름이나 삼항식은 None."""
    assert eval_const(expr, env) == exp


# ------------------------------------------------------------ 포트
def test_ansi_ports_basic():
    """기본 ANSI 포트: 이름, 방향, 폭, output reg, [msb:lsb]를 정확히 추출하고 주석은 무시한다."""
    m = parse_modules("""
module m (
    input clk, // clock
    input [7:0] din,
    output reg [3:0] q,
    output done
);
endmodule
""")[0]
    assert m.name == "m" and m.warnings == []
    assert [(p.name, p.direction, p.width) for p in m.ports] == [
        ("clk", "input", 1), ("din", "input", 8), ("q", "output", 4), ("done", "output", 1)]
    assert port(m, "q").is_reg and not port(m, "done").is_reg
    assert (port(m, "din").msb, port(m, "din").lsb) == (7, 0)


def test_direction_and_range_carry_over_to_following_names():
    """`input [7:0] a, b, c`처럼 방향과 범위가 뒤따르는 이름에 이어진다 (새 방향이 나오면 바뀐다)."""
    m = parse_modules("module m(input [7:0] a, b, c, output x, y); endmodule")[0]
    assert [(p.name, p.direction, p.width) for p in m.ports] == [
        ("a", "input", 8), ("b", "input", 8), ("c", "input", 8),
        ("x", "output", 1), ("y", "output", 1)]


def test_wire_signed_and_ascending_range():
    """wire/logic, signed, 오름차순 범위 [0:3]도 처리한다 (폭은 |msb-lsb|+1)."""
    m = parse_modules("module m(input wire signed [0:3] a, output logic [1:0] b); endmodule")[0]
    assert port(m, "a").signed and port(m, "a").width == 4
    assert (port(m, "a").msb, port(m, "a").lsb) == (0, 3)
    assert port(m, "b").width == 2


def test_port_line_numbers_point_to_original_source():
    """포트와 모듈의 줄 번호가 주석과 빈 줄을 포함한 원본 기준이다."""
    m = parse_modules("// c\nmodule m (\n  input a,\n\n  input b\n);\nendmodule")[0]
    assert m.line == 2
    assert (port(m, "a").line, port(m, "b").line) == (3, 5)


def test_commented_out_port_is_ignored():
    """주석 처리된 포트 선언(// 와 /* */)은 포트로 잡지 않는다."""
    m = parse_modules("module m(\n input a,\n // input hidden,\n /* output x, */\n input b);\nendmodule")[0]
    assert [p.name for p in m.ports] == ["a", "b"]


# ------------------------------------------------------------ 파라미터
def test_header_parameters_and_port_width_from_params():
    """#(parameter ...) 헤더 파라미터와 localparam $clog2를 계산해서 포트 폭에 반영한다."""
    m = parse_modules("""
module fifo #(parameter DATA_W = 8, parameter DEPTH = 16, localparam AW = $clog2(DEPTH))
(
    input [DATA_W-1:0] din,
    output [AW-1:0] level
);
endmodule
""")[0]
    assert [(p.name, p.value) for p in m.params] == [("DATA_W", 8), ("DEPTH", 16), ("AW", 4)]
    assert m.params[2].local is True
    assert port(m, "din").width == 8 and port(m, "level").width == 4


def test_parameter_list_without_repeated_keyword_and_body_params():
    """`parameter A=1, B=2` 쉼표 목록과 본문의 parameter/localparam(앞 값을 참조하는 식 포함)을 처리한다."""
    m = parse_modules("""
module m #(parameter A = 1, B = 2) (input x);
    parameter C = A + B;
    localparam D = C * 2, E = 5;
endmodule
""")[0]
    assert {p.name: p.value for p in m.params} == {"A": 1, "B": 2, "C": 3, "D": 6, "E": 5}
    assert {p.name for p in m.params if p.local} == {"D", "E"}


def test_unresolvable_width_is_none_with_warning():
    """폭을 계산할 수 없으면 추측하지 않고 width=None과 경고를 남긴다."""
    m = parse_modules("module m(input [UNKNOWN-1:0] a); endmodule")[0]
    assert port(m, "a").width is None
    assert any("폭" in w for w in m.warnings)


# ------------------------------------------------------------ 모듈 / 한계
def test_multiple_modules_in_one_file():
    """한 파일에 모듈이 여러 개여도 각각 따로 추출한다."""
    mods = parse_modules("module a(input x); endmodule\nmodule b(output y); endmodule\n")
    assert [m.name for m in mods] == ["a", "b"]
    assert mods[0].ports[0].name == "x" and mods[1].ports[0].name == "y"


def test_module_without_ports():
    """포트가 없는 모듈(testbench)은 포트 0개, 경고 없음."""
    m = parse_modules("module tb; initial $finish; endmodule")[0]
    assert m.name == "tb" and m.ports == [] and m.warnings == []


def test_non_ansi_ports_warn_instead_of_guessing():
    """비ANSI 포트 선언은 지원 범위 밖이므로 포트를 비우고 경고한다 (추측하지 않음)."""
    m = parse_modules("module m(a, b);\n input a;\n output b;\nendmodule")[0]
    assert m.ports == []
    assert any("비ANSI" in w for w in m.warnings)


def test_generate_and_macro_warn():
    """generate 블록은 해석하지 않으므로 경고로 알린다."""
    m = parse_modules("module m(input a);\n generate endgenerate\nendmodule")[0]
    assert any("generate" in w for w in m.warnings)


def test_crlf_source():
    """Windows 줄바꿈(CRLF) 소스에서도 포트와 줄 번호가 같게 나온다."""
    m = parse_modules("module m (\r\n input a,\r\n output [3:0] b\r\n);\r\nendmodule\r\n")[0]
    assert [(p.name, p.width) for p in m.ports] == [("a", 1), ("b", 4)]
    assert port(m, "b").line == 3


# ------------------------------------------------------------ 실제 DUT
@pytest.mark.skipif(not SYNC.exists(), reason="dut/sync_fifo/rtl 없음")
def test_golden_sync_fifo_modules_and_ports():
    """실제 골든 sync FIFO 3개 모듈의 포트 이름, 방향, 폭, reg 여부가 소스와 일치한다."""
    mods = {m.name: m for m in parse_files(sorted(SYNC.glob("*.v")))}
    assert set(mods) == {"sync_fifo", "fifo_ctrl", "fifo_mem"}
    assert all(m.warnings == [] for m in mods.values())

    top = mods["sync_fifo"]
    assert [(p.name, p.direction, p.width) for p in top.ports] == [
        ("ck", "input", 1), ("reset", "input", 1), ("wr_en", "input", 1), ("rd_en", "input", 1),
        ("data_in", "input", 8), ("data_out", "output", 8), ("full", "output", 1), ("empty", "output", 1)]

    ctrl = mods["fifo_ctrl"]
    assert (port(ctrl, "wr_ptr").width, port(ctrl, "wr_ptr").is_reg) == (3, True)
    assert port(ctrl, "full").direction == "output"

    mem = mods["fifo_mem"]
    assert (port(mem, "data_out").width, port(mem, "data_out").is_reg) == (8, True)
    assert port(mem, "rd_addr").width == 3