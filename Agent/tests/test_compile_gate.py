"""TB Generator 6-3: Compile Gate (xvlog -> xelab).

앞부분은 run_tool을 가짜로 바꿔(monkeypatch) 게이트의 조율 로직과 에러 파서를 검증한다 (Vivado 불필요).
에러 문구는 실제 xvlog가 LLM TB에 대해 낸 출력을 그대로 썼다.
마지막 3개는 실제 Vivado로 확인한다 (Vivado가 없으면 건너뜀).
"""

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.compile_gate import (CompileError, CompileResult, compile_check, parse_compile_errors,
                               tb_top_of)

ROOT = Path(__file__).resolve().parents[1]

# 실제 xvlog 출력 (LLM이 만든 TB의 103행에서 이름 없는 블록 안에 reg를 선언했을 때)
XVLOG_FAIL = """\
INFO: [VRFC 10-2263] Analyzing Verilog file "C:/Users/Junyoung/Desktop/Verilog/Agent/runs/tb/sync_fifo_llm.v" into library work
INFO: [VRFC 10-311] analyzing module tb_sync_fifo
ERROR: [VRFC 10-8885] declarations are not allowed in an unnamed block [C:/Users/Junyoung/Desktop/Verilog/Agent/runs/tb/sync_fifo_llm.v:103]
ERROR: [VRFC 10-8530] module 'tb_sync_fifo' is ignored due to previous errors [C:/Users/Junyoung/Desktop/Verilog/Agent/runs/tb/sync_fifo_llm.v:9]
"""
XELAB_FAIL = """\
ERROR: [VRFC 10-2063] Module <fifo_zzz> not found while processing module instance <c1> [C:/x/sync_fifo.v:20]
ERROR: [XSIM 43-3322] Static elaboration of top level Verilog design unit(s) in library work failed.
"""

TB = "module tb_x;\n  reg a;\n  initial $finish;\nendmodule\n"


def step(rc=0, out="", timed_out=False):
    """run_tool이 돌려주는 StepResult 대역 (게이트가 읽는 속성만)."""
    return SimpleNamespace(returncode=rc, stdout=out, duration_s=0.5, timed_out=timed_out)


def fake_tools(monkeypatch, **per_tool):
    """도구 이름별 결과를 돌려주고 호출 기록(이름, 인자, cwd)을 남기는 가짜 run_tool을 설치한다."""
    calls = []

    def fake(name, args, cwd, timeout=None):
        calls.append((name, list(args), cwd))
        return per_tool.get(name, step())

    monkeypatch.setattr("core.compile_gate.run_tool", fake)
    return calls


@pytest.fixture
def rtl(tmp_path):
    f = tmp_path / "dut.v"
    f.write_text("module dut; endmodule\n")
    return [f]


# ------------------------------------------------------------ 에러 파서
def test_parse_extracts_code_message_file_and_line_from_real_output():
    """실제 xvlog 출력에서 코드, 메시지, 파일, 줄 번호를 읽는다 (Windows 경로의 드라이브 콜론 포함)."""
    errs = parse_compile_errors(XVLOG_FAIL, "xvlog")
    assert len(errs) == 2
    e = errs[0]
    assert e.code == "VRFC 10-8885" and e.message == "declarations are not allowed in an unnamed block"
    assert e.file.endswith("sync_fifo_llm.v") and e.line == 103 and e.stage == "xvlog"


def test_parse_marks_derived_errors_as_not_primary():
    """'ignored due to previous errors'는 앞선 에러의 결과이므로 primary=False다."""
    a, b = parse_compile_errors(XVLOG_FAIL, "xvlog")
    assert a.primary and not b.primary


def test_parse_marks_elaboration_failed_summary_as_derived():
    """xelab의 'Static elaboration ... failed'는 요약 줄이라 원인이 아니다."""
    a, b = parse_compile_errors(XELAB_FAIL, "xelab")
    assert a.primary and a.code == "VRFC 10-2063" and not b.primary


def test_parse_error_without_location():
    """[파일:줄]이 없는 에러도 파싱되고 file, line은 None이다."""
    e = parse_compile_errors("ERROR: [VRFC 10-1234] something odd\n", "xvlog")[0]
    assert e.message == "something odd" and e.file is None and e.line is None


def test_parse_ignores_info_and_warning_lines():
    """INFO와 WARNING 줄은 에러로 읽지 않는다."""
    text = "INFO: [VRFC 10-311] analyzing module a\nWARNING: [VRFC 10-3091] something\n"
    assert parse_compile_errors(text, "xvlog") == []


def test_compile_error_str_is_readable():
    """에러는 단계, 코드, 메시지, 파일:줄이 한 줄로 보인다."""
    e = CompileError("xvlog", "VRFC 10-8885", "msg", file="C:/a/b/tb.v", line=7)
    assert str(e) == "[xvlog] VRFC 10-8885: msg (tb.v:7)"


def test_tb_top_of_takes_first_module():
    """xelab의 top은 코드의 첫 module 이름이다."""
    assert tb_top_of("`timescale 1ns/1ps\nmodule tb_a;\nendmodule\nmodule b; endmodule") == "tb_a"
    assert tb_top_of("no module here") is None
    assert tb_top_of("// module in_comment\nmodule real_one;\nendmodule") == "real_one"


# ------------------------------------------------------------ 게이트 조율 (가짜 run_tool)
def test_success_runs_xvlog_then_xelab(tmp_path, rtl, monkeypatch):
    """둘 다 성공하면 xvlog -> xelab 순서이고 ok다. xelab에는 TB top과 스냅샷 이름이 간다."""
    calls = fake_tools(monkeypatch)
    r = compile_check(rtl, TB, None, tmp_path / "w")
    assert r.ok and r.stage is None and r.errors == []
    assert [c[0] for c in calls] == ["xvlog", "xelab"]
    assert calls[1][1] == ["tb_x", "-s", "gate_snap"]


def test_tb_file_is_written_exactly_and_listed_last(tmp_path, rtl, monkeypatch):
    """TB는 받은 코드 그대로(머리말 없이) 파일로 쓰고, RTL 뒤에 마지막 인자로 넘긴다 (줄 번호 일치)."""
    calls = fake_tools(monkeypatch)
    r = compile_check(rtl, TB, "tb_x", tmp_path / "w")
    assert Path(r.tb_file).read_text(encoding="utf-8") == TB
    args = calls[0][1]
    assert args[-1] == r.tb_file and Path(args[0]).is_absolute() and Path(args[0]).name == "dut.v"


def test_default_mode_is_plain_verilog(tmp_path, rtl, monkeypatch):
    """기본은 -sv 없이 Verilog 모드로 컴파일한다."""
    calls = fake_tools(monkeypatch)
    compile_check(rtl, TB, None, tmp_path / "w")
    assert "-sv" not in calls[0][1]


def test_sv_flag_is_passed_to_xvlog_only(tmp_path, rtl, monkeypatch):
    """sv=True면 평가 흐름과 같은 `xvlog -sv`로 돌린다 (xelab에는 붙이지 않음)."""
    calls = fake_tools(monkeypatch)
    r = compile_check(rtl, TB, None, tmp_path / "w", sv=True)
    assert calls[0][1][0] == "-sv" and "-sv" not in calls[1][1] and r.sv


def test_xvlog_failure_stops_before_xelab(tmp_path, rtl, monkeypatch):
    """xvlog가 실패하면 xelab은 돌리지 않고, 실패 단계와 에러, 원본 출력을 돌려준다."""
    calls = fake_tools(monkeypatch, xvlog=step(1, XVLOG_FAIL))
    r = compile_check(rtl, TB, None, tmp_path / "w")
    assert not r.ok and r.stage == "xvlog" and [c[0] for c in calls] == ["xvlog"]
    assert r.errors[0].code == "VRFC 10-8885" and "unnamed block" in r.stdout


def test_xelab_failure_is_reported_with_its_stage(tmp_path, rtl, monkeypatch):
    """xvlog는 통과하고 xelab에서 모듈을 못 찾으면 stage가 xelab이다."""
    fake_tools(monkeypatch, xelab=step(1, XELAB_FAIL))
    r = compile_check(rtl, TB, None, tmp_path / "w")
    assert not r.ok and r.stage == "xelab" and r.errors[0].code == "VRFC 10-2063"


def test_primary_errors_drops_derived(tmp_path, rtl, monkeypatch):
    """primary_errors()는 파생 메시지를 뺀 원인만 돌려준다."""
    fake_tools(monkeypatch, xvlog=step(1, XVLOG_FAIL))
    r = compile_check(rtl, TB, None, tmp_path / "w")
    assert [e.code for e in r.primary_errors()] == ["VRFC 10-8885"]


def test_error_lines_with_zero_exit_code_still_fail(tmp_path, rtl, monkeypatch):
    """종료 코드가 0이어도 ERROR 줄이 있으면 실패다 (도구 종료 코드만 믿지 않음)."""
    fake_tools(monkeypatch, xvlog=step(0, XVLOG_FAIL))
    assert not compile_check(rtl, TB, None, tmp_path / "w").ok


def test_nonzero_exit_without_error_lines_gets_generic_error(tmp_path, rtl, monkeypatch):
    """종료 코드만 실패이고 ERROR 줄이 없으면 일반 에러 한 건으로 기록한다."""
    fake_tools(monkeypatch, xvlog=step(2, "weird output"))
    r = compile_check(rtl, TB, None, tmp_path / "w")
    assert not r.ok and "종료 코드 2" in r.errors[0].message


def test_timeout_is_a_failure_with_timeout_error(tmp_path, rtl, monkeypatch):
    """타임아웃이면 실패이고 TIMEOUT 에러가 붙는다."""
    fake_tools(monkeypatch, xvlog=step(None, "", timed_out=True))
    r = compile_check(rtl, TB, None, tmp_path / "w")
    assert not r.ok and r.timed_out and r.errors[-1].code == "TIMEOUT"


def test_code_without_module_fails_without_running_tools(tmp_path, rtl, monkeypatch):
    """module이 없는 코드는 도구를 돌리지 않고 바로 실패한다."""
    calls = fake_tools(monkeypatch)
    r = compile_check(rtl, "// nothing", None, tmp_path / "w")
    assert not r.ok and calls == []


def test_missing_tool_propagates_as_file_not_found(tmp_path, rtl, monkeypatch):
    """도구가 PATH에 없으면 환경 문제이므로 결과가 아니라 FileNotFoundError다."""
    def boom(name, args, cwd, timeout=None):
        raise FileNotFoundError(name)
    monkeypatch.setattr("core.compile_gate.run_tool", boom)
    with pytest.raises(FileNotFoundError):
        compile_check(rtl, TB, None, tmp_path / "w")


def test_each_call_gets_its_own_workdir(tmp_path, rtl, monkeypatch):
    """호출마다 새 작업 폴더를 쓴다 (이전 시도의 산출물이 다음 시도를 가리지 않게)."""
    fake_tools(monkeypatch)
    a = compile_check(rtl, TB, None, tmp_path / "w")
    b = compile_check(rtl, TB, None, tmp_path / "w")
    assert a.workdir != b.workdir and Path(a.workdir).is_dir() and Path(b.workdir).is_dir()


def test_duration_is_sum_of_steps(tmp_path, rtl, monkeypatch):
    """소요 시간은 실행한 단계의 합이다."""
    fake_tools(monkeypatch)
    assert compile_check(rtl, TB, None, tmp_path / "w").duration_s == pytest.approx(1.0)


# ------------------------------------------------------------ 실제 Vivado
needs_vivado = pytest.mark.skipif(shutil.which("xvlog") is None or shutil.which("xelab") is None,
                                  reason="Vivado 없음")


@pytest.fixture
def real_rtl():
    d = ROOT / "dut" / "sync_fifo" / "rtl"
    if not d.is_dir():
        pytest.skip("dut/sync_fifo가 없음")
    return sorted(d.glob("*.v"))


@needs_vivado
def test_real_unnamed_block_declaration_fails_in_verilog_mode(tmp_path):
    """실제 xvlog: 이름 없는 블록 안의 선언은 Verilog 모드에서 VRFC 10-8885로 실패한다 (LLM TB에서 실제로 나온 에러)."""
    tb = ("module tb_bad;\n  reg ck;\n  always @(posedge ck) begin\n    reg x;\n    x = 1;\n  end\n"
          "  initial $finish;\nendmodule\n")
    r = compile_check([], tb, None, tmp_path / "w")
    assert not r.ok and r.stage == "xvlog"
    assert "VRFC 10-8885" in {e.code for e in r.primary_errors()}
    assert r.primary_errors()[0].line == 4


@needs_vivado
def test_real_minimal_tb_passes_both_stages(tmp_path):
    """실제 Vivado: 문제없는 최소 TB는 xvlog와 xelab을 모두 통과한다."""
    r = compile_check([], TB, None, tmp_path / "w")
    assert r.ok, r.stdout


@needs_vivado
def test_real_human_tb_passes_gate_in_flow_mode(tmp_path, real_rtl):
    """Phase 4에서 직접 쓴 self-checking TB는 평가 흐름과 같은 -sv 모드에서 게이트를 통과한다."""
    tb = (ROOT / "dut/sync_fifo/tb/tb_sync_fifo_sc.v").read_text(encoding="utf-8")
    r = compile_check(real_rtl, tb, None, tmp_path / "w", sv=True)
    assert r.ok, r.stdout