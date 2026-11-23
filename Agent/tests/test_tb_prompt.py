"""TB Generator 6-2: 프롬프트 빌더와 소스 로더.

LLM을 부르지 않고 "무엇이 프롬프트에 들어가는가"만 검증한다.
핵심은 (1) 코드가 아는 사실이 그대로 들어가고 (2) 만들 수 없는 요약은 거부하고 (3) 같은 입력은 같은 프롬프트다.
"""

import copy
import json
from pathlib import Path

import pytest

from core.rtl_summary import summarize_rtl
from core.tb_prompt import TBPromptError, build_tb_prompt, load_sources, tb_module_name

DUT = """\
module counter(input ck, input reset, input en, output reg [3:0] count);
  always @(posedge ck or posedge reset)
    if (reset) count <= 0; else if (en) count <= count + 1;
endmodule
"""


def make(tmp_path, text=DUT, top="counter"):
    f = tmp_path / "counter.v"
    f.write_text(text)
    s = summarize_rtl([f], top=top)
    return s, {f.as_posix(): text}


def facts_of(prompt: str) -> dict:
    """프롬프트의 FACTS JSON 블록을 읽어 dict로 되돌린다."""
    start = prompt.index("```json") + len("```json")
    return json.loads(prompt[start: prompt.index("```", start)])


def test_tb_module_name_uses_top(tmp_path):
    """TB 모듈 이름은 tb_<top>으로 정해진다."""
    s, _ = make(tmp_path)
    assert tb_module_name(s) == "tb_counter"


def test_prompt_contains_parser_facts_verbatim(tmp_path):
    """FACTS에 포트, 구동/관찰 대상, 클럭, 리셋이 파서가 뽑은 그대로 들어간다."""
    s, src = make(tmp_path)
    _, prompt = build_tb_prompt(s, src)
    f = facts_of(prompt)
    assert f["top"] == "counter"
    assert f["inputs_to_drive"] == ["en"] and f["outputs_to_observe"] == ["count"]
    assert f["clocks"][0]["port"] == "ck" and f["resets"][0]["port"] == "reset"
    assert {"name": "count", "direction": "output", "width": 4} in f["ports"]


def test_prompt_facts_leave_out_bulky_fields(tmp_path):
    """계층 트리, 해시, 경고 원문 같은 큰 필드는 FACTS에 넣지 않는다 (토큰 절약)."""
    s, src = make(tmp_path)
    f = facts_of(build_tb_prompt(s, src)[1])
    assert not ({"sources", "modules", "hierarchy", "warnings", "blockers"} & set(f))


def test_prompt_includes_every_source_file(tmp_path):
    """모든 RTL 소스가 파일 이름 제목과 함께 들어간다."""
    s, src = make(tmp_path)
    _, prompt = build_tb_prompt(s, src)
    assert "### counter.v" in prompt and "count <= count + 1" in prompt


def test_system_prompt_states_facts_are_authoritative(tmp_path):
    """system 프롬프트는 포트/폭/클럭을 지어내지 말라고 못 박는다."""
    s, src = make(tmp_path)
    system, _ = build_tb_prompt(s, src)
    assert "authoritative" in system and "Never invent" in system


def test_spec_text_is_included_when_given(tmp_path):
    """명세를 주면 SPEC 절에 그대로 들어가고, 가정 목록을 요구하는 문구는 나오지 않는다."""
    s, src = make(tmp_path)
    _, prompt = build_tb_prompt(s, src, spec_text="count는 en일 때 1 증가한다.")
    assert "## SPEC (intended behaviour" in prompt and "count는 en일 때 1 증가한다." in prompt
    assert "No separate specification" not in prompt


def test_without_spec_prompt_asks_for_assumptions(tmp_path):
    """명세가 없으면 RTL에서 동작을 유도하되 가정을 // ASSUMPTIONS: 로 남기게 한다."""
    s, src = make(tmp_path)
    _, prompt = build_tb_prompt(s, src, spec_text="   ")
    assert "No separate specification" in prompt and "// ASSUMPTIONS:" in prompt


def test_timescale_rule_when_rtl_has_none(tmp_path):
    """RTL에 timescale이 없으면 TB에 쓰지 말라는 규칙이 들어간다 (XSIM 43-4099 방지)."""
    s, src = make(tmp_path)
    _, prompt = build_tb_prompt(s, src)
    assert "Do NOT write any `timescale" in prompt and "43-4099" in prompt


def test_timescale_rule_when_rtl_has_it(tmp_path):
    """RTL에 timescale이 있으면 TB 첫 줄에 정확히 그 지시문을 쓰라고 한다."""
    s, src = make(tmp_path, "`timescale 1ns/1ps\n" + DUT)
    _, prompt = build_tb_prompt(s, src)
    assert "must be exactly: `timescale 1ns/1ps" in prompt


def test_contract_has_log_protocol_and_dut_name(tmp_path):
    """출력 규약에 [TB] PASS/FAIL, CHECK_FAIL, CHECKS, DUT 인스턴스 이름이 정확한 문구로 들어간다."""
    s, src = make(tmp_path)
    _, p = build_tb_prompt(s, src)
    for text in ('$display("[TB] PASS");', "[TB] FAIL:", "CHECK_FAIL t=%0t sig=", "CHECKS total=",
                 "`tb_counter`", "counter dut (...)", "$random(seed)"):
        assert text in p


def test_contract_requires_timeformat_so_times_are_readable(tmp_path):
    """규약이 $timeformat 호출을 요구한다 (없으면 CHECK_FAIL 시각에 단위가 없어 하네스가 읽지 못함)."""
    s, src = make(tmp_path)
    assert '$timeformat(-9, 0, " ns", 0);' in build_tb_prompt(s, src)[1]


def test_contract_tells_not_to_compare_outputs_that_are_undefined(tmp_path):
    """계약이 '정의되지 않은 출력(예: 첫 read 전의 메모리 출력)은 valid 플래그로 막고 기대값을 추측으로 초기화하지 말라'고 한다.
    (LLM TB가 기대값을 0으로 초기화해 DUT의 X와 비교하다 골든에서 FAIL한 실제 사례)"""
    s, src = make(tmp_path)
    p = build_tb_prompt(s, src)[1]
    assert "undefined until some event" in p and "`valid` flag" in p and "`X !== 0` is a mismatch" in p


def test_contract_warns_about_signed_random_and_unnamed_block_declarations(tmp_path):
    """계약이 부호 있는 $random 나머지(확률 왜곡)와 이름 없는 블록 안의 선언(xvlog 거부)을 명시적으로 금지한다."""
    s, src = make(tmp_path)
    p = build_tb_prompt(s, src)[1]
    assert "`$random` is SIGNED" in p and "({$random(seed)} % 10) < 8" in p
    assert "never declare variables inside an unnamed begin/end block" in p


def test_reset_rule_describes_polarity_and_kind(tmp_path):
    """리셋 규칙에 극성과 비동기 여부가 파서 값대로 서술된다."""
    s, src = make(tmp_path)
    _, p = build_tb_prompt(s, src)
    assert "active-high (1 = reset), asynchronous" in p


def test_active_low_sync_reset_rule(tmp_path):
    """active-low 동기 리셋 DUT는 그렇게 서술된다."""
    dut = ("module d(input ck, input rst_n, input a, output reg q);\n"
           "  always @(posedge ck) if (!rst_n) q <= 0; else q <= a;\nendmodule\n")
    s, src = make(tmp_path, dut, "d")
    _, p = build_tb_prompt(s, src)
    assert "active-low (0 = reset), synchronous" in p


def test_no_clock_is_treated_as_combinational(tmp_path):
    """클럭이 없는 설계는 조합 회로로 다루라는 지시가 들어간다."""
    s, src = make(tmp_path, "module g(input a, input b, output y); assign y = a & b; endmodule\n", "g")
    _, p = build_tb_prompt(s, src)
    assert "no clock port" in p and "combinational" in p


def test_multi_clock_gets_independent_generators(tmp_path):
    """클럭이 둘이면 서로 다른 주기의 독립 생성기를 요구한다."""
    dut = ("module d(input wr_ck, input rd_ck, input a, output reg q, output reg r);\n"
           "  always @(posedge wr_ck) q <= a;\n  always @(posedge rd_ck) r <= q;\nendmodule\n")
    s, src = make(tmp_path, dut, "d")
    assert s["multi_clock"]
    _, p = build_tb_prompt(s, src)
    import re
    periods = {m.group(2): m.group(1) for m in re.finditer(r"always #(\d+) (\w+) = ~\2;", p)}
    assert set(periods) == {"wr_ck", "rd_ck"} and len(set(periods.values())) == 2   # 클럭마다 주기가 다름
    assert "independent generator" in p


def test_not_ready_summary_is_rejected_with_reasons(tmp_path):
    """blockers가 있는 요약은 프롬프트를 만들지 않고 사유를 알려 준다."""
    s, src = make(tmp_path)
    s["ready_for_tb"] = False
    s["blockers"] = ["timescale이 일부 모듈에만 있음"]
    with pytest.raises(TBPromptError, match="timescale이 일부"):
        build_tb_prompt(s, src)


def test_invalid_summary_schema_is_rejected(tmp_path):
    """스키마가 깨진 요약은 거부한다."""
    s, src = make(tmp_path)
    broken = copy.deepcopy(s)
    del broken["ports"]
    with pytest.raises(TBPromptError, match="스키마"):
        build_tb_prompt(broken, src)


def test_empty_sources_are_rejected(tmp_path):
    """소스가 하나도 없으면 거부한다."""
    s, _ = make(tmp_path)
    with pytest.raises(TBPromptError, match="비어"):
        build_tb_prompt(s, {})


def test_same_input_gives_identical_prompt(tmp_path):
    """같은 입력이면 프롬프트가 바이트 단위로 같다 (캐시 적중과 재현성의 전제)."""
    s, src = make(tmp_path)
    assert build_tb_prompt(s, src, "spec") == build_tb_prompt(copy.deepcopy(s), dict(src), "spec")


# ------------------------------------------------------------ 소스 로더
def test_load_sources_reads_files_matching_summary(tmp_path):
    """summary의 경로를 읽고, 해시가 맞으면 내용을 그대로 돌려준다."""
    s, src = make(tmp_path)
    assert load_sources(s) == src


def test_load_sources_rejects_changed_rtl(tmp_path):
    """요약을 만든 뒤 RTL이 바뀌었으면 거부한다 (낡은 요약으로 TB를 만들지 않기 위함)."""
    s, _ = make(tmp_path)
    Path(s["sources"][0]["path"]).write_text(DUT + "// edited\n")
    with pytest.raises(TBPromptError, match="바뀜"):
        load_sources(s)


def test_load_sources_rejects_missing_file(tmp_path):
    """소스 파일이 사라졌으면 거부한다."""
    s, _ = make(tmp_path)
    Path(s["sources"][0]["path"]).unlink()
    with pytest.raises(TBPromptError, match="없음"):
        load_sources(s)


def test_load_sources_resolves_relative_to_base(tmp_path):
    """상대 경로 요약은 base 폴더를 기준으로 읽는다."""
    f = tmp_path / "counter.v"
    f.write_text(DUT)
    s = summarize_rtl([f], top="counter")
    s["sources"][0]["path"] = "counter.v"
    assert load_sources(s, base=tmp_path) == {"counter.v": DUT}


def test_load_sources_normalizes_crlf_but_hash_uses_raw_bytes(tmp_path):
    """CRLF 파일도 해시 검증을 통과하고, 프롬프트용 텍스트는 \\n으로 통일된다 (OS가 달라도 같은 프롬프트)."""
    f = tmp_path / "counter.v"
    f.write_bytes(DUT.replace("\n", "\r\n").encode())
    s = summarize_rtl([f], top="counter")
    assert load_sources(s) == {f.as_posix(): DUT}