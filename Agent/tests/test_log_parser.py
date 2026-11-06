from pathlib import Path

from core.log_parser import parse_xvlog

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