"""RTL Analyzer 5-4: LLM에 넘길 요약 JSON의 내용, 스키마 검증, TB 생성 차단 조건."""

import copy
import json
from pathlib import Path

import pytest

from core.rtl_analyzer import parse_modules
from core.rtl_summary import SCHEMA_VERSION, summarize_modules, summarize_rtl, validate_summary
from scripts import make_rtl_summary

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "dut" / "sync_fifo" / "rtl"
ASYNC = ROOT / "Manual_test" / "dut"


def summ(src, top=None):
    return summarize_modules(parse_modules(src), top=top)


SEQ = """
module core(input clk, input rst_n, input [7:0] d, output reg [7:0] q);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) q <= 0; else q <= d;
    end
endmodule
"""


# ------------------------------------------------------------ 내용
def test_basic_summary_fields():
    """단일 모듈: top, 포트, 구동/관측 대상(클럭과 리셋은 구동 목록에서 제외), 클럭, 리셋, 준비 상태."""
    s = summ(SEQ)
    assert s["top"] == "core" and s["schema_version"] == SCHEMA_VERSION
    assert [(p["name"], p["direction"], p["width"]) for p in s["ports"]] == [
        ("clk", "input", 1), ("rst_n", "input", 1), ("d", "input", 8), ("q", "output", 8)]
    assert s["inputs_to_drive"] == ["d"] and s["outputs_to_observe"] == ["q"]
    assert s["clocks"] == [{"port": "clk", "edges": ["posedge"]}]
    assert s["resets"] == [{"port": "rst_n", "active_high": False, "asynchronous": True,
                            "evidence": "sensitivity+if"}]
    assert s["ready_for_tb"] is True and s["blockers"] == []
    assert validate_summary(s) == []


def test_parameters_of_top_are_listed():
    """top의 파라미터를 기본값(원문 식)과 계산된 값으로 함께 담는다."""
    s = summ("module m #(parameter W = 8, localparam AW = $clog2(16)) (input [W-1:0] a); endmodule")
    assert s["parameters"] == [{"name": "W", "default": "8", "value": 8, "local": False},
                               {"name": "AW", "default": "$clog2(16)", "value": 4, "local": True}]
    assert s["ports"][0]["width"] == 8


def test_hierarchy_tree_is_nested():
    """계층은 {module, instance, children} 중첩 구조이고 정의 없는 모듈은 defined=False로 표시한다."""
    s = summ("module c(input a); endmodule\nmodule t(input a); c u1 (.a(a)); ip u2 (.a(a)); endmodule")
    kids = s["hierarchy"]["children"]
    assert [(k["instance"], k["module"]) for k in kids] == [("u1", "c"), ("u2", "ip")]
    assert kids[1].get("defined") is False


def test_summary_is_json_serializable_and_roundtrips():
    """요약은 순수 JSON 타입만 써서 직렬화한 뒤 다시 읽어도 같다."""
    s = summ(SEQ)
    assert json.loads(json.dumps(s, ensure_ascii=False)) == s


def test_summary_is_deterministic():
    """같은 입력이면 요약이 항상 같다 (LLM 호출 전 캐시 키로 쓸 수 있다)."""
    assert summ(SEQ) == summ(SEQ)


# ------------------------------------------------------------ timescale
def test_timescale_directive_for_tb():
    """설계에 timescale이 없으면 TB 지시문은 빈 문자열, 모두 있으면 top의 값을 따른다."""
    child = "module c(input a); endmodule\n"
    top = "module t(input a); c u (.a(a)); endmodule\n"
    assert summ(child + top)["timescale"] == {"status": "none", "value": None, "tb_directive": ""}
    ts = summ("`timescale 1ns/1ps\n" + child + top)["timescale"]
    assert ts == {"status": "all", "value": "1ns/1ps", "tb_directive": "`timescale 1ns/1ps"}


def test_mixed_timescale_blocks_tb_generation():
    """일부 모듈에만 timescale이 있으면 TB에 어떤 값을 써도 xelab이 실패하므로 차단한다."""
    s = summ("module c(input a); endmodule\n`timescale 1ns/1ps\nmodule t(input a); c u (.a(a)); endmodule")
    assert s["ready_for_tb"] is False and s["timescale"]["tb_directive"] is None
    assert any("timescale" in b for b in s["blockers"])
    assert validate_summary(s) == []


def test_different_timescale_values_are_noted_not_blocked():
    """모듈마다 값이 다르지만 모두 있으면 막지 않고 note로 남긴다."""
    s = summ("`timescale 1ns/1ps\nmodule c(input a); endmodule\n`timescale 1ns/1ns\n"
             "module t(input a); c u (.a(a)); endmodule")
    assert s["ready_for_tb"] is True and s["timescale"]["value"] == "1ns/1ns"
    assert any("timescale 값이 다름" in n for n in s["notes"])


# ------------------------------------------------------------ 차단과 참고
def test_unknown_port_width_blocks():
    """top 포트의 폭을 계산하지 못하면 TB를 만들 수 없으므로 차단한다."""
    s = summ("module m(input [UNKNOWN-1:0] a); endmodule")
    assert s["ready_for_tb"] is False and any("폭" in b for b in s["blockers"])


def test_unresolved_module_blocks():
    """정의가 없는 하위 모듈(IP)이 있으면 시뮬레이션할 수 없으므로 차단한다."""
    s = summ("module t(input a); vendor_ip u (.a(a)); endmodule")
    assert any("vendor_ip" in b for b in s["blockers"])


def test_connection_error_blocks():
    """자식에 없는 포트에 연결하면 컴파일이 실패하므로 차단한다."""
    s = summ("module c(input a); endmodule\nmodule t(input a); c u (.a(a), .typo(a)); endmodule")
    assert any("unknown_port" in b for b in s["blockers"])


def test_non_ansi_top_blocks():
    """비ANSI 포트 선언은 포트를 추출하지 못하므로 차단한다."""
    s = summ("module m(a, b);\n input a;\n output b;\nendmodule")
    assert any("비ANSI" in b for b in s["blockers"])


def test_combinational_design_is_not_blocked_but_noted():
    """클럭이 없는 조합 회로는 막지 않고 note로 남긴다."""
    s = summ("module g(input [3:0] b, output [3:0] y); assign y = b; endmodule")
    assert s["ready_for_tb"] is True and s["clocks"] == [] and s["resets"] == []
    assert any("클럭을 찾지 못함" in n for n in s["notes"])
    assert any("리셋을 찾지 못함" in n for n in s["notes"])


def test_weak_reset_evidence_is_noted():
    """리셋 판별 근거가 sensitivity+if가 아니면 note로 약한 근거임을 알린다."""
    s = summ("module m(input clk, input rst, input d, output reg q);\n"
             "always @(posedge clk or posedge rst) q <= d;\nendmodule")
    assert any("근거가 약함" in n for n in s["notes"])


def test_multi_clock_is_noted():
    """클럭이 둘 이상이면 note로 알린다."""
    s = summ("module m(input a_ck, input b_ck, input d, output reg q, output reg r);\n"
             "always @(posedge a_ck) q <= d;\nalways @(posedge b_ck) r <= d;\nendmodule")
    assert s["multi_clock"] is True and any("클럭이 2개" in n for n in s["notes"])


# ------------------------------------------------------------ top 선택
def test_ambiguous_top_gives_skeleton_that_still_validates():
    """top 후보가 여럿이면 값을 비운 요약(top=None, ready_for_tb=False)을 돌려주고 스키마는 지킨다."""
    s = summ("module a(input x); endmodule\nmodule b(input y); endmodule")
    assert s["top"] is None and s["ready_for_tb"] is False
    assert any("후보" in b for b in s["blockers"])
    assert validate_summary(s) == []


def test_explicit_top_overrides_and_unknown_top_blocks():
    """top을 직접 지정하면 그 모듈로 요약하고, 없는 이름을 지정하면 차단한다."""
    src = "module a(input x); endmodule\nmodule b(input y, input z); endmodule"
    assert summ(src, top="b")["top"] == "b" and len(summ(src, top="b")["ports"]) == 2
    s = summ(src, top="nope")
    assert s["top"] is None and any("nope" in b for b in s["blockers"])


# ------------------------------------------------------------ 스키마 검증
def test_validate_accepts_good_and_rejects_bad_summaries():
    """키 누락, 타입 오류, 알 수 없는 키, 포트 목록과 어긋난 참조, ready/blockers 불일치를 각각 잡는다."""
    good = summ(SEQ)
    assert validate_summary(good) == []

    bad = copy.deepcopy(good); del bad["ports"]
    assert any("키 누락" in e for e in validate_summary(bad))

    bad = copy.deepcopy(good); bad["multi_clock"] = "no"
    assert any("multi_clock" in e for e in validate_summary(bad))

    bad = copy.deepcopy(good); bad["extra"] = 1
    assert any("알 수 없는 키" in e for e in validate_summary(bad))

    bad = copy.deepcopy(good); bad["inputs_to_drive"].append("ghost")
    assert any("ghost" in e for e in validate_summary(bad))

    bad = copy.deepcopy(good); bad["clocks"][0]["port"] = "ghost"
    assert any("클럭" in e for e in validate_summary(bad))

    bad = copy.deepcopy(good); bad["ready_for_tb"] = False
    assert any("ready_for_tb" in e for e in validate_summary(bad))

    bad = copy.deepcopy(good); bad["ports"][0]["direction"] = "sideways"
    assert any("ports[0]" in e for e in validate_summary(bad))

    bad = copy.deepcopy(good); bad["schema_version"] = 99
    assert any("schema_version" in e for e in validate_summary(bad))

    assert validate_summary("not a dict") == ["요약이 dict가 아님"]


# ------------------------------------------------------------ 파일 / CLI
def test_summarize_rtl_records_source_hashes(tmp_path):
    """파일로 요약하면 sources에 경로와 내용 해시(12자리)가 기록되고, 내용이 바뀌면 해시가 바뀐다."""
    f = tmp_path / "m.v"
    f.write_text("module m(input a); endmodule\n")
    h1 = summarize_rtl([f])["sources"][0]["sha256"]
    f.write_text("module m(input a, input b); endmodule\n")
    s2 = summarize_rtl([f])
    assert len(h1) == 12 and s2["sources"][0]["sha256"] != h1 and len(s2["ports"]) == 2


def test_cli_writes_json_and_reports_status(tmp_path, capsys):
    """CLI는 --out 경로에 JSON을 쓰고 top과 ready_for_tb를 표준 에러로 알린다 (스키마가 맞으면 종료 코드 0)."""
    f = tmp_path / "m.v"
    f.write_text(SEQ)
    out = tmp_path / "sub" / "s.json"
    assert make_rtl_summary.main([str(f), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["top"] == "core"
    assert "ready_for_tb: True" in capsys.readouterr().err


# ------------------------------------------------------------ 실제 DUT (5-3 출력으로 확인한 사실)
@pytest.mark.skipif(not SYNC.exists(), reason="dut/sync_fifo/rtl 없음")
def test_golden_sync_fifo_summary():
    """골든 sync FIFO: 단일 클럭 ck, 비동기 active-high reset, timescale 없음(TB 지시문 빈 문자열), TB 생성 가능."""
    s = summarize_rtl(sorted(SYNC.glob("*.v")))
    assert validate_summary(s) == []
    assert s["top"] == "sync_fifo" and s["ready_for_tb"] is True
    assert s["inputs_to_drive"] == ["wr_en", "rd_en", "data_in"]
    assert s["outputs_to_observe"] == ["data_out", "full", "empty"]
    assert s["clocks"] == [{"port": "ck", "edges": ["posedge"]}] and s["multi_clock"] is False
    assert s["resets"][0]["port"] == "reset" and s["resets"][0]["asynchronous"] is True
    assert s["timescale"] == {"status": "none", "value": None, "tb_directive": ""}
    assert [(c["instance"], c["module"]) for c in s["hierarchy"]["children"]] == [
        ("c1", "fifo_ctrl"), ("m1", "fifo_mem")]
    assert s["warnings"] == [] and s["notes"] == []


@pytest.mark.skipif(not ASYNC.exists(), reason="Manual_test/dut 없음")
def test_async_fifo_summary():
    """async FIFO: 클럭 2개(wr_ck, rd_ck), 비동기 active-high reset, timescale 1ns/1ps(TB 지시문 포함), 중첩 계층."""
    s = summarize_rtl(sorted(ASYNC.rglob("*.v")))
    assert validate_summary(s) == []
    assert s["top"] == "async_fifo" and s["ready_for_tb"] is True
    assert [(p["name"], p["width"]) for p in s["ports"]] == [
        ("wr_ck", 1), ("rd_ck", 1), ("reset", 1), ("wr_en", 1), ("rd_en", 1),
        ("data_in", 8), ("data_out", 8), ("full", 1), ("empty", 1)]
    assert s["inputs_to_drive"] == ["wr_en", "rd_en", "data_in"]
    assert [c["port"] for c in s["clocks"]] == ["rd_ck", "wr_ck"] and s["multi_clock"] is True
    assert [(r["port"], r["active_high"], r["asynchronous"]) for r in s["resets"]] == [("reset", True, True)]
    assert s["timescale"] == {"status": "all", "value": "1ns/1ps", "tb_directive": "`timescale 1ns/1ps"}
    ctrl = next(k for k in s["hierarchy"]["children"] if k["instance"] == "c1")
    assert [(k["instance"], k["module"]) for k in ctrl["children"]] == [
        ("wr_gray1", "bin2gray"), ("rd_gray1", "bin2gray"), ("sync_rd2wr", "synchronizer"),
        ("sync_wr2rd", "synchronizer"), ("wr_gray2", "bin2gray")]
    assert any("클럭이 2개" in n for n in s["notes"])