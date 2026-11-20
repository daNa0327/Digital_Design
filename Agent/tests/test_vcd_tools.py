"""Agent용 VCD 도구 테스트: 길이 제한, 오류를 dict로 반환, alias/status 동반."""

import json
from pathlib import Path

import pytest

from core.vcd_reader import VcdReader
from core.vcd_tools import MAX_CHANGES, TOOL_SPECS, VcdTools, dispatch

SAMPLE = Path(__file__).parent / "data" / "ok_async_fifo.vcd"


def _vcd(n_edges: int = 30) -> str:
    """clk(tb.clk/dut.clk는 같은 ID), 같은 이력의 다른 ID(tb.en/dut.en), 8비트 d, 항상 x인 dead."""
    head = ("$timescale 1ps $end\n$scope module tb $end\n$var wire 1 ! clk $end\n"
            "$var wire 1 e en $end\n$var reg 8 # d [7:0] $end\n$scope module dut $end\n"
            "$var wire 1 ! clk $end\n$var wire 1 f en $end\n$var wire 1 x dead $end\n"
            "$upscope $end\n$upscope $end\n$enddefinitions $end\n")
    body = "#0\n0!\n0e\n0f\nb0 #\nxx\n"
    for i in range(1, n_edges + 1):
        body += f"#{i * 10}\n{i % 2}!\n{i % 2}e\n{i % 2}f\nb{i:b} #\n"
    return head + body


@pytest.fixture
def tools():
    return VcdTools(VcdReader.from_text(_vcd()))


def test_list_signals_filter_and_truncation(tools):
    """pattern 필터와 limit 초과 시 truncated 표시."""
    out = tools.list_signals("clk")
    assert out["total"] == 2 and not out["truncated"]
    assert {s["name"] for s in out["signals"]} == {"tb.clk", "tb.dut.clk"}
    assert tools.list_signals(limit=2)["truncated"] is True


def test_read_signal_includes_status_alias_and_candidates(tools):
    """같은 ID는 aliases, ID가 다르고 이력이 같으면 same_history_candidates로 함께 반환된다."""
    out = tools.read_vcd_signal("tb.en", 0, 30)
    assert out["status"] == "ok"
    assert out["same_history_candidates"] == ["tb.dut.en"]
    assert tools.read_vcd_signal("tb.clk", 0, 30)["aliases"] == ["tb.dut.clk"]
    assert out["changes"][0] == {"t_ps": 0, "value": "0"}


def test_read_signal_truncation_gives_next_t0(tools):
    """max_changes를 넘으면 truncated와 이어서 읽을 next_t0_ps를 알려 준다."""
    out = tools.read_vcd_signal("tb.clk", 0, 300, max_changes=5)
    assert out["truncated"] and len(out["changes"]) == 5
    assert out["total_in_window"] == 31
    assert out["next_t0_ps"] == 50
    nxt = tools.read_vcd_signal("tb.clk", out["next_t0_ps"], 300, max_changes=5)
    assert nxt["changes"][0]["t_ps"] == 50


def test_hard_cap_is_enforced(tools):
    """LLM이 큰 값을 요청해도 상한(MAX_CHANGES)을 넘기지 않는다."""
    big = VcdTools(VcdReader.from_text(_vcd(500)))
    out = big.read_vcd_signal("tb.clk", 0, None, max_changes=10_000)
    assert len(out["changes"]) == MAX_CHANGES and out["truncated"]


def test_unknown_signal_returns_error_with_suggestions(tools):
    """없는 이름은 예외가 아니라 error + 비슷한 이름 제안."""
    out = tools.read_vcd_signal("tb.dut.clkk", 0, 10)
    assert "error" in out
    out = tools.read_vcd_signal("top.clk", 0, 10)
    assert "tb.clk" in out["suggestions"]
    assert out["status"] == "not_in_vcd"


def test_value_formats_and_x_stays_binary(tools):
    """벡터는 hex/dec로 표기하고, x가 섞이면 이진 문자열 그대로, 상태 코드는 always_x."""
    out = tools.read_vcd_signal("tb.d", 20, 20, fmt="hex")
    assert out["changes"][0]["value"] == "0x2"
    assert tools.read_vcd_signal("tb.d", 20, 20, fmt="dec")["changes"][0]["value"] == "2"
    assert tools.read_vcd_signal("tb.dut.dead", 0, 10)["status"] == "always_x"


def test_sample_signals_rows_and_truncation(tools):
    """에지 직전 값 표. max_rows로 자르면 next_t0_ps를 준다."""
    out = tools.sample_signals("tb.clk", ["tb.en", "tb.d"], 0, 100)
    assert out["rows"][0] == {"t_ps": 10, "values": {"tb.en": "0", "tb.d": "00000000"}}
    cut = tools.sample_signals("tb.clk", ["tb.en"], max_rows=3)
    assert cut["truncated"] and len(cut["rows"]) == 3 and cut["next_t0_ps"] == 70
    assert "error" in tools.sample_signals("tb.clk", ["tb.nope"])
    assert "error" in tools.sample_signals("tb.clk", [f"tb.en"] * 11)


def test_dispatch_never_raises(tools):
    """알 수 없는 도구, 잘못된 인자, 내부 오류 모두 error dict로 돌려준다."""
    assert "available" in dispatch(tools, "delete_everything", {})
    assert "error" in dispatch(tools, "read_vcd_signal", {})
    assert "error" in dispatch(tools, "read_vcd_signal", {"name": "tb.clk", "bogus": 1})
    assert dispatch(tools, "list_signals", {"pattern": "en"})["total"] == 2
    json.dumps(dispatch(tools, "read_vcd_signal", {"name": "tb.clk"}))   # JSON 직렬화 가능


def test_tool_specs_match_methods():
    """TOOL_SPECS의 이름과 필수 인자가 실제 메서드와 맞는다."""
    t = VcdTools(VcdReader.from_text(_vcd()))
    for spec in TOOL_SPECS:
        assert callable(getattr(t, spec["name"]))
        assert spec["input_schema"]["type"] == "object"


@pytest.mark.skipif(not SAMPLE.exists(), reason="샘플 VCD 없음")
def test_real_sample_output_is_small():
    """실제 VCD의 wr_ck 50ns 구간 응답은 JSON 3000자 이내이고 dut.wr_ck가 후보에 포함된다."""
    t = VcdTools(VcdReader.from_file(SAMPLE))
    out = t.read_vcd_signal("async_fifo_tb.wr_ck", 0, 50_000)
    assert len(json.dumps(out)) < 3000
    assert "async_fifo_tb.dut.wr_ck" in out["aliases"] + out["same_history_candidates"]