"""VcdReader 테스트. 작은 VCD 텍스트로 규칙을 검증하고, 마지막에 실제 샘플 VCD로 확인한다."""

from pathlib import Path

import pytest

from core.vcd_reader import VcdReader

VCD = """$timescale 1ps $end
$scope module tb $end
$var wire 1 ! clk $end
$var reg 8 # data [7:0] $end
$scope module dut $end
$var wire 1 ! clk $end
$var wire 1 $ en $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
b0 #
x$
$end
#5000
1!
b101 #
#10000
0!
1$
#15000
bx #
"""

SAMPLE = Path(__file__).parent / "data" / "ok_async_fifo.vcd"


def test_header_timescale_names_and_info():
    """타임스케일, 전체 계층 이름, 폭/종류가 헤더에서 읽힌다."""
    r = VcdReader.from_text(VCD)
    assert r.timescale_ps == 1
    assert set(r.names()) == {"tb.clk", "tb.data", "tb.dut.clk", "tb.dut.en"}
    s = r.info("tb.data")
    assert (s.width, s.kind, s.id) == (8, "reg", "#")


def test_timescale_ns_scales_times_to_ps():
    """1ns 타임스케일이면 #5는 5000ps로 변환된다."""
    r = VcdReader.from_text("$timescale 1 ns $end\n$scope module t $end\n$var wire 1 ! a $end\n"
                            "$upscope $end\n$enddefinitions $end\n#0\n0!\n#5\n1!\n")
    assert r.timescale_ps == 1000
    assert r.changes("t.a") == [(0, "0"), (5000, "1")]
    assert r.end_time_ps == 5000


def test_alias_shares_id_and_history():
    """같은 ID를 쓰는 두 이름은 서로 alias이고 이력이 같다 (덮어써지지 않음)."""
    r = VcdReader.from_text(VCD)
    assert r.aliases("tb.clk") == ["tb.dut.clk"]
    assert r.aliases("tb.dut.en") == []
    assert r.changes("tb.clk") == r.changes("tb.dut.clk")
    assert r.changes("tb.clk") == [(0, "0"), (5000, "1"), (10000, "0")]


def test_value_at_semantics():
    """첫 변화 이전은 None, 변화 시각 정각은 새 값, 그 사이는 직전 값."""
    r = VcdReader.from_text(VCD)
    assert r.value_at("tb.dut.en", 0) == "x"
    assert r.value_at("tb.clk", 4999) == "0"
    assert r.value_at("tb.clk", 5000) == "1"
    assert r.value_at("tb.clk", 99999) == "0"
    r2 = VcdReader.from_text("$timescale 1ps $end\n$scope module t $end\n$var wire 1 ! a $end\n"
                             "$upscope $end\n$enddefinitions $end\n#100\n1!\n")
    assert r2.value_at("t.a", 50) is None


def test_vector_padding_and_to_int():
    """벡터는 폭에 맞게 확장된다(b101 -> 00000101). x가 있으면 to_int는 None."""
    r = VcdReader.from_text(VCD)
    assert r.value_at("tb.data", 5000) == "00000101"
    assert r.to_int(r.value_at("tb.data", 5000)) == 5
    assert r.value_at("tb.data", 15000) == "xxxxxxxx"
    assert r.to_int(r.value_at("tb.data", 15000)) is None
    assert r.to_int(None) is None


def test_window_with_and_without_initial():
    """window는 구간 안의 변화만 주고, include_initial이면 시작 시점의 값을 앞에 붙인다."""
    r = VcdReader.from_text(VCD)
    assert r.window("tb.clk", 6000, 12000, include_initial=False) == [(10000, "0")]
    assert r.window("tb.clk", 6000, 12000) == [(6000, "1"), (10000, "0")]
    assert r.window("tb.clk", 5000, 5000) == [(5000, "1")]


def test_end_time_is_last_timestamp():
    """end_time_ps는 마지막 타임스탬프다 (시뮬레이션 종료 시각이 아님)."""
    assert VcdReader.from_text(VCD).end_time_ps == 15000


def test_truncated_file_is_tolerated():
    """줄바꿈 없이 잘린 마지막 줄(불완전한 값)은 버리고 나머지는 정상 읽는다."""
    cut = VCD + "#20000\n1"          # 마지막 줄이 값만 있고 ID도, 줄바꿈도 없음
    r = VcdReader.from_text(cut)
    assert r.end_time_ps == 20000    # 완전한 '#20000' 줄은 유지
    assert r.changes("tb.clk")[-1] == (10000, "0")   # 잘린 '1' 줄은 값으로 반영되지 않음


def test_unknown_name_raises_keyerror():
    """없는 신호 이름은 KeyError로 알려 준다."""
    r = VcdReader.from_text(VCD)
    with pytest.raises(KeyError):
        r.value_at("tb.nope", 0)
    assert r.find("clk") == ["tb.clk", "tb.dut.clk"]


@pytest.mark.skipif(not SAMPLE.exists(), reason="샘플 VCD 없음")
def test_real_sample_vcd():
    """실제 async FIFO VCD: 1ps 해상도, 마지막 타임스탬프 400ns, wr_ck의 alias와 별도 ID가 구분된다."""
    r = VcdReader.from_file(SAMPLE)
    assert r.timescale_ps == 1
    assert r.end_time_ps == 400_000
    wr = r.find("wr_ck")
    assert len(wr) >= 2
    ids = {r.info(n).id for n in wr}
    assert len(ids) >= 2                       # tb.wr_ck는 별도 ID
    assert any(r.aliases(n) for n in wr)       # dut/c1/m1은 ID를 공유