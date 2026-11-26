"""Phase 8-2: UART DUT(사용자 UART_mid-bit 골든 RTL, self-checking TB, 변형 카탈로그).

확인 사항
- 카탈로그의 find가 골든 RTL에 expect_count번 나타나고 모든 변형이 패치된다.
- (Icarus가 있으면) 골든은 TB를 PASS하고, 동등 변형을 뺀 모든 변형은 TB가 FAIL시킨다.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from core.bugs import apply_bug, default_human_tb, load_catalog

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "dut" / "uart" / "rtl"
TB = ROOT / "dut" / "uart" / "tb" / "tb_uart_sc.v"
CAT = ROOT / "bugs" / "uart" / "bugs.json"
needs_iverilog = pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog 없음")


def run_iverilog(files, tmp_path, name="x", tb=TB):
    """TB에 timescale이 없으므로 기본값(1ns)을 맞추는 지시문 파일을 앞에 붙여 Icarus로 실행하고 로그를 돌려준다."""
    ts = tmp_path / "ts.v"
    ts.write_text("`timescale 1ns/1ps\n")
    out = tmp_path / name
    r = subprocess.run(["iverilog", "-g2005", "-o", str(out), str(ts), *map(str, files), str(tb)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run(["vvp", str(out)], capture_output=True, text=True, timeout=120).stdout


def test_카탈로그는_골든에_적용되고_메타가_맞다(tmp_path):
    meta = json.loads(CAT.read_text(encoding="utf-8"))
    assert (meta["dut"], meta["dut_top"], meta["top"]) == ("uart", "UART", "uart_sc_tb")
    assert default_human_tb(RTL, "uart") == TB
    bugs = load_catalog(CAT)
    assert len(bugs) == 32 and sum(b.equivalent for b in bugs) == 2
    names = sorted(p.name for p in RTL.glob("*.v"))
    for b in bugs:
        ap = apply_bug(b, RTL, tmp_path / b.id)
        assert sorted(p.name for p in ap.rtl_dir.glob("*.v")) == names and ap.line >= 1


@needs_iverilog
def test_골든은_PASS하고_모든_시나리오가_실행된다(tmp_path):
    out = run_iverilog(sorted(RTL.glob("*.v")), tmp_path)
    assert "[TB] PASS" in out and "CHECK_FAIL" not in out
    m = re.search(r"CHECKS total=(\d+) mismatches=(\d+)", out)
    assert int(m.group(1)) > 700 and m.group(2) == "0"
    c = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", re.search(r"COVER .*", out).group(0))}
    assert c["rx_tol"] >= 6 and c["frame_err"] >= 2 and c["held"] >= 1 and c["midreset"] >= 2 and c["loop"] >= 4


@needs_iverilog
def test_동등_변형을_뺀_모든_변형을_TB가_잡는다(tmp_path):
    survived, wrongly_caught = [], []
    for b in load_catalog(CAT):
        ap = apply_bug(b, RTL, tmp_path / b.id)
        failed = "[TB] FAIL" in run_iverilog(sorted(ap.rtl_dir.glob("*.v")), tmp_path, b.id + ".out")
        if b.equivalent and failed:
            wrongly_caught.append(b.id)
        if not b.equivalent and not failed:
            survived.append(b.id)
    assert survived == [] and wrongly_caught == []
