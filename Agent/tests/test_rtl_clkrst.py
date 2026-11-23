"""RTL Analyzer 5-3: 클럭/리셋 판별, timescale, top 인터페이스 요약."""

from pathlib import Path

import pytest

from core.rtl_analyzer import parse_modules, parse_files, build_hierarchy, top_interface

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "dut" / "sync_fifo" / "rtl"
ASYNC = ROOT / "Manual_test" / "dut"


def mod(body, ports="input clk, input rst, input d, output reg q"):
    return parse_modules(f"module m({ports});\n{body}\nendmodule")[0]


def rst(m, name):
    return next(r for r in m.resets if r.name == name)


# ------------------------------------------------------------ 비동기 리셋
def test_async_active_high_reset_confirmed_by_first_if():
    """`posedge clk or posedge rst` + 첫 if가 rst를 검사 -> 클럭 clk, 비동기 active-high 리셋 (근거 sensitivity+if)."""
    m = mod("always @(posedge clk or posedge rst) begin if (rst) q <= 0; else q <= d; end")
    assert [(c.name, c.edge) for c in m.clocks] == [("clk", "posedge")]
    r = rst(m, "rst")
    assert (r.active_high, r.asynchronous, r.evidence) == (True, True, "sensitivity+if")
    assert m.warnings == []


def test_async_active_low_reset():
    """`negedge rst_n`은 active-low 비동기 리셋이다 (`if (!rst_n)`과 극성이 일치)."""
    m = mod("always @(posedge clk or negedge rst_n) begin if (!rst_n) q <= 0; else q <= d; end",
            "input clk, input rst_n, input d, output reg q")
    r = rst(m, "rst_n")
    assert (r.active_high, r.asynchronous) == (False, True)
    assert m.warnings == []


def test_sensitivity_list_order_does_not_matter():
    """리셋이 감도 목록의 앞에 와도(`or` 대신 `,` 포함) 클럭과 리셋을 구분한다."""
    m = mod("always @(negedge rst, posedge clk) begin if (~rst) q <= 0; else q <= d; end")
    assert [c.name for c in m.clocks] == ["clk"] and rst(m, "rst").active_high is False


def test_two_edges_decided_by_name_when_first_if_is_not_reset():
    """첫 if가 리셋을 검사하지 않으면 이름(rst/reset 등)으로 고르고 근거를 sensitivity+name으로 기록한다."""
    m = mod("always @(posedge clk or posedge rst) begin q <= d; end")
    assert rst(m, "rst").evidence == "sensitivity+name"


def test_ambiguous_two_edges_are_not_classified():
    """두 에지 신호의 이름이 둘 다 클럭/리셋 단서가 없으면 분류하지 않고 경고한다."""
    m = mod("always @(posedge a or posedge b) begin q <= d; end", "input a, input b, input d, output reg q")
    assert m.clocks == [] and m.resets == []
    assert any("구분하지 못함" in w for w in m.warnings)


def test_polarity_mismatch_warns():
    """에지는 negedge(active-low)인데 if 조건은 active-high 식이면 경고한다."""
    m = mod("always @(posedge clk or negedge rst) begin if (rst) q <= 0; else q <= d; end")
    assert any("극성" in w for w in m.warnings)


# ------------------------------------------------------------ 동기 리셋 / 클럭만
def test_sync_reset_from_first_if_and_name():
    """에지가 하나인 블록의 첫 if가 리셋 이름 신호를 검사하면 동기 리셋으로 본다 (근거 if+name)."""
    m = mod("always @(posedge clk) begin if (!rst) q <= 0; else q <= d; end")
    r = rst(m, "rst")
    assert (r.active_high, r.asynchronous, r.evidence) == (False, False, "if+name")


def test_clock_only_block_has_no_reset():
    """첫 if가 리셋이 아닌 신호(wr_en 등)를 검사하면 리셋로 오인하지 않는다."""
    m = mod("always @(posedge clk) begin if (d) q <= 1; end")
    assert [c.name for c in m.clocks] == ["clk"] and m.resets == []


def test_combinational_blocks_are_ignored():
    """`always @*`, `always @(*)`, 레벨 감도 목록은 클럭/리셋 판별에서 제외한다."""
    m = mod("always @* q = d; always @(*) q = d; always @(d or rst) q = d;")
    assert m.clocks == [] and m.resets == [] and m.warnings == []


def test_same_clock_used_by_two_blocks_is_merged():
    """같은 클럭을 쓰는 always 블록이 여럿이면 하나로 합치고 uses를 센다."""
    m = mod("always @(posedge clk) q <= d;\nalways @(posedge clk) q <= q;")
    assert len(m.clocks) == 1 and m.clocks[0].uses == 2 and len(m.clocks[0].lines) == 2


def test_posedge_and_negedge_of_same_clock_are_kept_separately():
    """같은 신호의 posedge와 negedge는 별개 항목으로 둔다."""
    m = mod("always @(posedge clk) q <= d;\nalways @(negedge clk) q <= q;")
    assert sorted((c.name, c.edge) for c in m.clocks) == [("clk", "negedge"), ("clk", "posedge")]


def test_clock_that_is_not_a_port_warns():
    """포트가 아닌 신호를 클럭으로 쓰면(내부 생성 클럭) 경고한다."""
    m = mod("reg div; always @(posedge div) q <= d;")
    assert any("포트가 아님" in w for w in m.warnings)


def test_comments_do_not_create_clocks():
    """주석 처리된 always 블록은 무시한다."""
    m = mod("// always @(posedge clk) q <= d;\n/* always @(negedge clk) q <= d; */")
    assert m.clocks == []


# ------------------------------------------------------------ timescale
def test_timescale_is_per_module_and_normalized():
    """`timescale은 이후 모듈에 계속 적용되고, 새 지시문이 나오면 바뀌며, 공백은 정규화된다."""
    mods = parse_modules("module z; endmodule\n`timescale 1ns / 1ps\nmodule a; endmodule\n"
                         "`timescale 10ns/1ns\nmodule b; endmodule\nmodule c; endmodule")
    assert [(m.name, m.timescale) for m in mods] == [("z", None), ("a", "1ns/1ps"), ("b", "10ns/1ns"), ("c", "10ns/1ns")]


def _hier(src):
    return build_hierarchy(parse_modules(src))


def test_timescale_status_none_all_mixed():
    """설계 안의 모듈이 모두 없으면 none, 모두 있으면 all, 일부만 있으면 mixed + XSIM 43-4099 경고."""
    child = "module c(input a); endmodule\n"
    top = "module t(input a); c u (.a(a)); endmodule\n"
    ts = "`timescale 1ns/1ps\n"
    assert _hier(child + top).timescale_status == "none"
    assert _hier(ts + child + top).timescale_status == "all"
    h = _hier(child + ts + top)
    assert h.timescale_status == "mixed"
    assert any("43-4099" in w for w in h.warnings)


def test_testbench_timescale_does_not_count_against_design():
    """TB가 timescale을 가져도 TB는 설계(top에서 도달하는 모듈)가 아니라서 DUT의 status에 영향이 없다."""
    h = _hier("module c(input a); endmodule\nmodule t(input a); c u (.a(a)); endmodule\n"
              "`timescale 1ns/1ps\nmodule tb; reg a; t d (.a(a)); endmodule")
    assert h.best_top == "t" and h.timescale_status == "none"


# ------------------------------------------------------------ top 인터페이스
ASYNC_SRC = """
module sync_ff(input ck, input rst, input d, output reg q);
    always @(posedge ck or posedge rst) begin if (rst) q <= 0; else q <= d; end
endmodule
module core(input wr_ck, input rd_ck, input rst, input d, output q1, output q2);
    sync_ff a (.ck(wr_ck), .rst(rst), .d(d), .q(q1));
    sync_ff b (.ck(rd_ck), .rst(rst), .d(d), .q(q2));
endmodule
module top(input wr_ck, input rd_ck, input rst, input d, output q1, output q2);
    core c (.wr_ck(wr_ck), .rd_ck(rd_ck), .rst(rst), .d(d), .q1(q1), .q2(q2));
endmodule
"""


def test_clock_and_reset_propagate_to_top_ports_through_hierarchy():
    """top에 always가 없어도 자식의 클럭/리셋이 `.port(top_port)` 연결을 따라 top 포트로 전파된다 (클럭 2개 -> multi_clock)."""
    ti = top_interface(_hier(ASYNC_SRC))
    assert ti["top"] == "top"
    assert ti["clocks"] == [{"port": "rd_ck", "edges": ["posedge"]}, {"port": "wr_ck", "edges": ["posedge"]}]
    assert [(r["port"], r["active_high"], r["asynchronous"]) for r in ti["resets"]] == [("rst", True, True)]
    assert ti["multi_clock"] is True and ti["timescale"] == "none"


def test_non_clock_connections_do_not_propagate():
    """식이 단순한 포트 이름이 아니면(`~x`, 상수, 슬라이스) 전파하지 않는다."""
    ti = top_interface(_hier("""
module c(input ck); reg q; always @(posedge ck) q <= 1; endmodule
module t(input a, input b); c u (.ck(a & b)); endmodule"""))
    assert ti["clocks"] == [] and ti["multi_clock"] is False


def test_top_interface_without_top_is_none():
    """top을 정할 수 없으면 None을 돌려준다."""
    assert top_interface(_hier("module a(input x); endmodule\nmodule b(input y); endmodule")) is None


# ------------------------------------------------------------ 실제 DUT
@pytest.mark.skipif(not SYNC.exists(), reason="dut/sync_fifo/rtl 없음")
def test_golden_sync_fifo_interface():
    """골든 sync FIFO: 클럭 ck(posedge), 리셋 reset(비동기 active-high), timescale 없음, 단일 클럭."""
    h = build_hierarchy(parse_files(sorted(SYNC.glob("*.v"))))
    ti = top_interface(h)
    assert ti["clocks"] == [{"port": "ck", "edges": ["posedge"]}]
    assert ti["resets"] == [{"port": "reset", "active_high": True, "asynchronous": True,
                             "evidence": "sensitivity+if"}]
    assert ti["multi_clock"] is False and ti["timescale"] == "none"
    assert h.warnings == []


@pytest.mark.skipif(not ASYNC.exists(), reason="Manual_test/dut 없음")
def test_async_fifo_structure():
    """async FIFO: top은 async_fifo, 모듈 5개, 연결 문제 0건 (5-2 출력으로 확인한 사실)."""
    h = build_hierarchy(parse_files(sorted(ASYNC.rglob("*.v"))))
    assert h.best_top == "async_fifo"
    assert set(h.modules) == {"async_fifo", "bin2gray", "fifo_ctrl", "fifo_mem", "synchronizer"}
    assert h.issues == []