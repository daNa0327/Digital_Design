"""RTL Analyzer 5-2: 인스턴스 추출, 계층, top 추정, 포트 연결 점검."""

from pathlib import Path

import pytest

from core.rtl_analyzer import parse_modules, parse_files, build_hierarchy, render_tree

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "dut" / "sync_fifo" / "rtl"


def mod(text, name):
    return next(m for m in parse_modules(text) if m.name == name)


# ------------------------------------------------------------ 인스턴스 추출
def test_named_connections_and_line():
    """이름 연결 `.port(expr)`을 포트와 식으로 나누고 인스턴스의 줄 번호를 기록한다."""
    m = mod("""module top(input a);
    child u1 (
        .x(a),
        .y(w[3:0]),
        .z()
    );
endmodule""", "top")
    inst = m.instances[0]
    assert (inst.module, inst.name, inst.line) == ("child", "u1", 2)
    assert [(c.port, c.expr) for c in inst.connections] == [("x", "a"), ("y", "w[3:0]"), ("z", "")]


def test_positional_connections():
    """위치 연결은 port=None, positional=True로 기록한다."""
    inst = mod("module top; child u(a, b, 1'b0); endmodule", "top").instances[0]
    assert [(c.port, c.expr, c.positional) for c in inst.connections] == [
        (None, "a", True), (None, "b", True), (None, "1'b0", True)]


def test_parameter_override_and_array_and_multi_instances():
    """#(.W(8)) 오버라이드, 인스턴스 배열 [3:0], `a(...), b(...)` 쉼표 연결을 처리한다."""
    m = mod("""module top;
    fifo #(.W(8), .D(16)) f0 (.clk(clk));
    cell c [3:0] (.i(x));
    cell p (.i(a)), q (.i(b));
endmodule""", "top")
    assert [i.name for i in m.instances] == ["f0", "c", "p", "q"]
    assert m.instances[0].param_overrides == {"W": "8", "D": "16"}
    assert [i.module for i in m.instances] == ["fifo", "cell", "cell", "cell"]


def test_keywords_calls_and_system_tasks_are_not_instances():
    """always/if/case/assign, 함수/태스크 호출, $display, 게이트 프리미티브는 인스턴스가 아니다."""
    m = mod("""module top(input clk, input a);
    reg q; wire w;
    always @(posedge clk) begin
        if (a) q <= 1; else if (!a) q <= 0;
        case (a) 1'b0: q <= 0; default: q <= 1; endcase
        $display("x %d", q);
    end
    assign w = foo(a);
    and g1 (w, a, q);
    function integer f (input x); f = x; endfunction
    task t (input x); $finish; endtask
    real_child u (.a(a));
endmodule""", "top")
    assert [(i.module, i.name) for i in m.instances] == [("real_child", "u")]


def test_instances_inside_comments_are_ignored():
    """주석 처리된 인스턴스는 무시한다."""
    m = mod("module top;\n // child u1 (.a(a));\n /* child u2 (.a(a)); */\n child u3 (.a(a));\nendmodule", "top")
    assert [i.name for i in m.instances] == ["u3"]


def test_wildcard_connection_warns():
    """`.*` 와일드카드 연결은 해석하지 않고 경고한다."""
    m = mod("module top; child u (.*); endmodule", "top")
    assert any(".*" in w for w in m.warnings)


# ------------------------------------------------------------ 계층 / top 추정
SRC = """
module leaf(input a, output y); endmodule
module mid(input a, output y); leaf l1 (.a(a), .y(y)); endmodule
module top(input a, output y); mid m1 (.a(a), .y(y)); leaf l2 (.a(a), .y()); endmodule
"""


def build(src):
    return build_hierarchy(parse_modules(src))


def test_top_is_module_nobody_instantiates():
    """어떤 모듈도 인스턴스화하지 않는 모듈이 top이고, children이 등장 순서대로 계산된다."""
    h = build(SRC)
    assert h.best_top == "top" and h.top_candidates == ["top"]
    assert h.children == {"leaf": [], "mid": ["leaf"], "top": ["mid", "leaf"]}


def test_testbench_is_excluded_and_dut_stays_top():
    """RTL과 TB를 함께 줘도, 포트가 없고 인스턴스를 가진 모듈은 testbench로 분류하고 DUT를 top으로 고른다."""
    h = build(SRC + "module tb; reg a; wire y; top dut (.a(a), .y(y)); endmodule")
    assert h.testbench_like == ["tb"]
    assert h.top_candidates == ["top"] and h.best_top == "top"


def test_only_testbench_gives_no_top():
    """testbench만 있으면 top을 정하지 않고 경고한다."""
    h = build("module leaf(input a); endmodule\nmodule tb; reg a; leaf u (.a(a)); endmodule")
    assert h.best_top == "leaf"            # leaf는 tb만 부르므로 후보로 남는다
    h2 = build("module tb; leaf u (); endmodule")
    assert h2.best_top is None and any("testbench" in w for w in h2.warnings)


def test_multiple_tops_are_reported_not_guessed():
    """top 후보가 둘이면 하나를 고르지 않고 경고한다."""
    h = build("module a(input x); endmodule\nmodule b(input y); endmodule")
    assert h.best_top is None and h.top_candidates == ["a", "b"]
    assert any("여러 개" in w for w in h.warnings)


def test_unresolved_module_is_listed():
    """정의를 찾을 수 없는 모듈(IP, 라이브러리)은 unresolved와 경고로 남기고 계층에서 뺀다."""
    h = build("module top(input a); vendor_ip u (.a(a)); endmodule")
    assert h.unresolved == [("top", "u", "vendor_ip")]
    assert h.best_top == "top"
    assert any("vendor_ip" in w for w in h.warnings)


def test_cycle_is_detected():
    """순환 인스턴스화를 감지한다."""
    h = build("module a(input x); b u (.x(x)); endmodule\nmodule b(input x); a u (.x(x)); endmodule")
    assert any("순환" in w for w in h.warnings)


def test_duplicate_module_names_warn():
    """같은 이름의 모듈이 두 번 정의되면 경고하고 먼저 나온 것을 쓴다."""
    h = build("module a(input x); endmodule\nmodule a(input y); endmodule")
    assert list(h.modules) == ["a"] and h.modules["a"].ports[0].name == "x"
    assert any("중복" in w for w in h.warnings)


# ------------------------------------------------------------ 연결 점검
def kinds(h):
    return sorted((i["kind"], i["port"]) for i in h.issues)


def test_unknown_port_and_unconnected_port():
    """자식에 없는 포트에 연결하면 unknown_port, 연결하지 않은 포트는 unconnected."""
    h = build("""
module c(input a, input b, output y); endmodule
module top(input a); c u (.a(a), .typo(a)); endmodule
""")
    assert kinds(h) == [("unconnected", "b"), ("unconnected", "y"), ("unknown_port", "typo")]


def test_empty_connection_counts_as_unconnected():
    """`.y()`처럼 비워 둔 연결은 미연결로 본다."""
    h = build("module c(input a, output y); endmodule\nmodule top(input a); c u (.a(a), .y()); endmodule")
    assert kinds(h) == [("unconnected", "y")]


def test_positional_connections_map_by_order():
    """위치 연결은 자식 포트 순서로 대응시키고, 개수가 넘치면 too_many_positional."""
    h = build("module c(input a, output y); endmodule\nmodule top(input a); c u (a, w, z); endmodule")
    assert kinds(h) == [("too_many_positional", "#2")]


# ------------------------------------------------------------ 트리 출력
def test_render_tree():
    """top에서 시작하는 인스턴스 트리를 들여쓰기로 출력한다."""
    tree = render_tree(build(SRC))
    assert tree.splitlines()[0] == "top"
    assert "m1: mid" in tree and "l1: leaf" in tree and "l2: leaf" in tree
    assert tree.index("m1: mid") < tree.index("l1: leaf") < tree.index("l2: leaf")


# ------------------------------------------------------------ 실제 DUT
@pytest.mark.skipif(not SYNC.exists(), reason="dut/sync_fifo/rtl 없음")
def test_golden_sync_fifo_hierarchy():
    """골든 sync FIFO: top은 sync_fifo, 자식은 c1:fifo_ctrl과 m1:fifo_mem, 연결 문제는 0건."""
    h = build_hierarchy(parse_files(sorted(SYNC.glob("*.v"))))
    assert h.best_top == "sync_fifo"
    assert h.children["sync_fifo"] == ["fifo_ctrl", "fifo_mem"]
    assert [(i.name, i.module) for i in h.modules["sync_fifo"].instances] == [
        ("c1", "fifo_ctrl"), ("m1", "fifo_mem")]
    assert h.issues == [] and h.warnings == [] and h.unresolved == []
    assert render_tree(h).splitlines() == ["sync_fifo", "├─ c1: fifo_ctrl", "└─ m1: fifo_mem"]