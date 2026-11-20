from pathlib import Path

from core.log_parser import parse_xelab, parse_xsim, parse_xvlog, time_to_ps
DATA = Path(__file__).parent / "data"

def read(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8", errors="replace")

def test_xvlog_ok():
    info = parse_xvlog(read("xvlog_ok.log"))
    assert len(info.attempted_files) == 6
    assert info.errors == []
    assert info.modules == [
        "async_fifo", "bin2gray", "fifo_ctrl",
        "fifo_mem", "synchronizer", "async_fifo_tb",
    ]

def test_xvlog_syntax_error():
    info = parse_xvlog(read("xvlog_syntax_error.log"))
    assert len(info.attempted_files) == 4          # 4번째 파일에서 멈춤
    assert [e.code for e in info.errors] == [
        "VRFC 10-4982", "VRFC 10-8549", "VRFC 10-8530",
    ]
    assert all(e.stage == "xvlog" for e in info.errors)
    assert info.errors[0].is_primary is True
    assert info.errors[1].is_primary is False
    assert info.errors[0].line == 21
    assert info.errors[0].file.endswith("fifo_mem_err1.v")

def test_error_without_location():
    info = parse_xvlog("ERROR: [VRFC 10-1234] something odd\n")
    e = info.errors[0]
    assert e.message == "something odd"
    assert e.file is None and e.line is None

def test_xelab_ok():
    info = parse_xelab(read("xelab_ok.log"))
    assert info.modules == [
        "bin2gray", "synchronizer", "fifo_ctrl",
        "fifo_mem", "async_fifo", "async_fifo_tb",
    ]
    assert info.snapshot_built is True
    assert info.snapshot_name == "snap"
    assert info.time_resolution == "1ps"
    assert info.errors == []

def test_xelab_missing_top():
    info = parse_xelab(read("xelab_missing_top.log"))
    assert info.snapshot_built is False
    assert info.modules == []
    assert len(info.errors) == 1
    e = info.errors[0]
    assert e.stage == "xelab"
    assert e.code == "XSIM 43-3225"
    assert "Cannot find design unit" in e.message
    assert e.is_primary is True
    assert e.file is None and e.line is None

def test_time_to_ps():
    assert time_to_ps("402", "ns") == 402_000
    assert time_to_ps("1.5", "us") == 1_500_000
    assert time_to_ps("10", "ps") == 10
    assert time_to_ps("2", "ms") == 2_000_000_000
    assert time_to_ps("1", "parsec") is None

def test_xsim_ok_without_marker():
    info = parse_xsim(read("xsim_ok.log"))
    assert info.finish_time_ps == 402_000
    assert info.finish_line == 131
    assert info.tb_markers == []
    assert info.errors == []

def test_xsim_pass_marker():
    info = parse_xsim(read("xsim_pass_marker.log"))
    assert [v for v, _ in info.tb_markers] == ["PASS"]
    assert info.errors == []
    assert info.finish_time_ps == 402_000

def test_xsim_fail_marker():
    info = parse_xsim(read("xsim_fail_marker.log"))
    assert info.tb_markers == [("FAIL", "dummy check")]
    assert info.errors == []      # 마커 FAIL은 시뮬레이터 에러가 아님

def test_xsim_error():
    info = parse_xsim(read("xsim_error.log"))
    assert len(info.errors) == 1
    e = info.errors[0]
    assert e.stage == "xsim" and e.severity == "ERROR" and e.code is None
    assert e.message == "dummy error"
    assert e.time_ps == 402_000
    assert e.line == 131 and e.file.endswith("tb_error.v")
    assert e.is_primary is True
    assert info.finish_time_ps == 402_000      # $error는 시뮬레이션을 중단하지 않음

def test_xsim_fatal():
    info = parse_xsim(read("xsim_fatal.log"))
    e = info.errors[0]
    assert e.severity == "FATAL" and e.message == "dummy fatal"
    assert info.finish_time_ps == 402_000
    assert info.finish_file is None and info.finish_line is None   # File/Line 없는 형식

def test_xsim_pass_with_error_keeps_both_facts():
    info = parse_xsim(read("xsim_pass_with_error.log"))
    assert [v for v, _ in info.tb_markers] == ["PASS"]
    assert len(info.errors) == 1 and info.errors[0].message == "dummy error"
    # 최종 판정(FAIL이어야 함)은 2-5의 analyze()에서

def test_xsim_hang():
    info = parse_xsim(read("xsim_hang.log"))
    assert info.finish_time_ps is None
    assert info.errors == [] and info.tb_markers == []