"""Phase 8-2: I2C DUT(Claude가 사용자 스타일로 작성한 골든 RTL, self-checking TB, 변형 카탈로그).

확인 사항
- 카탈로그의 find가 골든 RTL에 expect_count번 나타나고 모든 변형이 패치된다. 파일/모듈 이름이 고유하다.
- (Icarus가 있으면) 골든은 TB를 PASS하고, 동등 변형을 뺀 모든 변형은 TB가 FAIL시킨다.
"""

import json
import re
import shutil
from pathlib import Path

import pytest

from core.bugs import apply_bug, default_human_tb, load_catalog
from tests.test_uart_dut import run_iverilog

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "dut" / "i2c" / "rtl"
TB = ROOT / "dut" / "i2c" / "tb" / "tb_i2c_sc.v"
CAT = ROOT / "bugs" / "i2c" / "bugs.json"
needs_iverilog = pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog 없음")


def test_카탈로그는_골든에_적용되고_메타와_이름이_맞다(tmp_path):
    meta = json.loads(CAT.read_text(encoding="utf-8"))
    assert (meta["dut"], meta["dut_top"], meta["top"]) == ("i2c", "i2c_system", "i2c_sc_tb")
    assert default_human_tb(RTL, "i2c") == TB
    modules = [m for p in RTL.glob("*.v") for m in re.findall(r"^\s*module\s+(\w+)", p.read_text(encoding="utf-8"), re.M)]
    assert len(modules) == len(set(modules)) and "i2c_system" in modules
    bugs = load_catalog(CAT)
    assert len(bugs) == 32 and sum(b.equivalent for b in bugs) == 2
    names = sorted(p.name for p in RTL.glob("*.v"))
    for b in bugs:
        ap = apply_bug(b, RTL, tmp_path / b.id)
        assert sorted(p.name for p in ap.rtl_dir.glob("*.v")) == names and ap.line >= 1


@needs_iverilog
def test_골든은_PASS하고_모든_시나리오가_실행된다(tmp_path):
    out = run_iverilog(sorted(RTL.glob("*.v")), tmp_path, tb=TB)
    assert "[TB] PASS" in out and "CHECK_FAIL" not in out
    m = re.search(r"CHECKS total=(\d+) mismatches=(\d+)", out)
    assert int(m.group(1)) > 2000 and m.group(2) == "0"
    c = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", re.search(r"COVER .*", out).group(0))}
    assert c["write"] >= 5 and c["read"] >= 5 and c["nack"] >= 3 and c["held"] >= 1 and c["midreset"] >= 3


@needs_iverilog
def test_동등_변형을_뺀_모든_변형을_TB가_잡는다(tmp_path):
    survived, wrongly_caught = [], []
    for b in load_catalog(CAT):
        ap = apply_bug(b, RTL, tmp_path / b.id)
        failed = "[TB] FAIL" in run_iverilog(sorted(ap.rtl_dir.glob("*.v")), tmp_path, b.id + ".out", tb=TB)
        if b.equivalent and failed:
            wrongly_caught.append(b.id)
        if not b.equivalent and not failed:
            survived.append(b.id)
    assert survived == [] and wrongly_caught == []
