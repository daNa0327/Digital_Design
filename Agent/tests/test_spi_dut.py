"""Phase 8-1: SPI DUT(골든 RTL, 사람 self-checking TB, 변형 카탈로그)와 DUT 일반화 옵션.

확인 사항
- 카탈로그의 find가 골든 RTL에 expect_count번 나타나고 모든 변형이 패치된다.
- (Icarus가 있으면) 골든은 TB를 PASS하고, 동등 변형을 뺀 모든 변형은 TB가 FAIL시킨다.
- 수정 전 골든(start 위상 버그)은 TB가 FAIL시킨다.
- `--dut` 옵션과 기본 TB 경로 규칙이 sync_fifo 기존 동작을 깨지 않는다.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from core.bugs import apply_bug, default_human_tb, load_catalog

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "dut" / "spi" / "rtl"
TB = ROOT / "dut" / "spi" / "tb" / "tb_spi_sc.v"
CAT = ROOT / "bugs" / "spi" / "bugs.json"
needs_iverilog = pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog 없음")


def run_iverilog(files, tmp_path, name="x"):
    """TB 파일에 timescale이 없으므로 시뮬레이터 기본값(1ns)을 맞추는 지시문 파일을 앞에 붙여 실행한다. 로그를 돌려준다."""
    ts = tmp_path / "ts.v"
    ts.write_text("`timescale 1ns/1ps\n")
    out = tmp_path / name
    r = subprocess.run(["iverilog", "-g2005", "-o", str(out), str(ts), *map(str, files), str(TB)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run(["vvp", str(out)], capture_output=True, text=True, timeout=120).stdout


def test_카탈로그의_find는_골든에_정확히_나타난다(tmp_path):
    """모든 변형이 골든 RTL에 적용된다 (find 개수 불일치면 apply_bug가 예외). 변형은 파일 구성이 골든과 같다."""
    bugs = load_catalog(CAT)
    assert len(bugs) == 32 and sum(b.equivalent for b in bugs) == 2
    names = sorted(p.name for p in RTL.glob("*.v"))
    for b in bugs:
        ap = apply_bug(b, RTL, tmp_path / b.id)
        assert sorted(p.name for p in ap.rtl_dir.glob("*.v")) == names and ap.line >= 1


def test_RTL_파일_이름은_모두_고유하다():
    """같은 이름의 파일이 둘이면 Agent의 논리 이름(rtl/<파일명>)이 모호해져 하네스가 거부한다 (SPI_RX.v가 둘이던 문제 재발 방지)."""
    names = [p.name for p in RTL.glob("*.v")]
    assert len(names) == len(set(names))
    modules = [m for p in RTL.glob("*.v") for m in re.findall(r"^\s*module\s+(\w+)", p.read_text(encoding="utf-8"), re.M)]
    assert len(modules) == len(set(modules)) and "spi_system" in modules


def test_카탈로그에_dut_top이_있다():
    """top 모듈(spi_system)과 TB top(spi_sc_tb)이 카탈로그에 있다. dut 이름과 top이 달라서 따로 둔다."""
    import json
    meta = json.loads(CAT.read_text(encoding="utf-8"))
    assert meta["dut_top"] == "spi_system" and meta["top"] == "spi_sc_tb" and meta["dut"] == "spi"


@needs_iverilog
def test_골든은_PASS하고_TB_로그_규약을_지킨다(tmp_path):
    """골든 PASS, mismatches=0, 검사 수가 충분하고, 모든 자극(위상 양쪽, done 중 start, 연속, 전송 중 리셋)이 실행된다."""
    out = run_iverilog(sorted(RTL.glob("*.v")), tmp_path)
    assert "[TB] PASS" in out and "CHECK_FAIL" not in out
    m = re.search(r"CHECKS total=(\d+) mismatches=(\d+)", out)
    assert int(m.group(1)) > 3000 and m.group(2) == "0"
    c = dict(re.findall(r"(\w+)=(\d+)", re.search(r"COVER .*", out).group(0)))
    assert int(c["start_spi_clk_high"]) > 10 and int(c["start_spi_clk_low"]) > 10
    assert int(c["restart_in_done"]) >= 2 and int(c["held"]) >= 3 and int(c["midreset"]) >= 3


@needs_iverilog
def test_동등_변형을_뺀_모든_변형을_TB가_잡는다(tmp_path):
    """30개 변형은 FAIL, 동등 변형 2개는 PASS여야 한다. TB가 잡지 못하는 변형이 생기면 TB를 보강하거나 동등 여부를 다시 판단한다."""
    survived, wrongly_caught = [], []
    for b in load_catalog(CAT):
        ap = apply_bug(b, RTL, tmp_path / b.id)
        out = run_iverilog(sorted(ap.rtl_dir.glob("*.v")), tmp_path, b.id + ".out")
        failed = "[TB] FAIL" in out
        if b.equivalent and failed:
            wrongly_caught.append(b.id)
        if not b.equivalent and not failed:
            survived.append(b.id)
    assert survived == [] and wrongly_caught == []


@needs_iverilog
def test_start_위상_버그가_있는_원본_골든은_TB가_잡는다(tmp_path):
    """start를 spi_clk 위상과 무관하게 CS에 쓰는 원본 Master_FSM은 start가 spi_clk high일 때 첫 비트가 밀린다. TB가 FAIL해야 한다."""
    src = (RTL / "Master_FSM.v").read_text(encoding="utf-8")
    orig = src.replace("start_q <= start && (state == IDLE);", "start_q <= 1'b0;")     # 자리만 막고
    orig = orig.replace("!start_q", "!start").replace("if (start_q)", "if (start)")        # 원본처럼 start를 바로 쓴다
    d = tmp_path / "orig"
    shutil.copytree(RTL, d)
    (d / "Master_FSM.v").write_text(orig, encoding="utf-8")
    out = run_iverilog(sorted(d.glob("*.v")), tmp_path, "orig.out")
    assert "[TB] FAIL" in out and "sig=MOSI" in out


# ---------------------------------------------------------------------------------------------
# DUT 일반화 옵션
# ---------------------------------------------------------------------------------------------
def test_기본_TB_경로는_dut_이름을_따르고_옛_이름도_허용한다(tmp_path):
    """tb_<dut>_sc.v가 있으면 그것을, tb_sync_fifo_sc.v만 있으면 그것을, 둘 다 없으면 새 이름 경로를 돌려준다."""
    g = tmp_path / "d" / "rtl"
    g.mkdir(parents=True)
    tb = tmp_path / "d" / "tb"
    tb.mkdir()
    assert default_human_tb(g, "spi") == tb / "tb_spi_sc.v"
    (tb / "tb_sync_fifo_sc.v").write_text("x")
    assert default_human_tb(g, "dut") == tb / "tb_sync_fifo_sc.v"
    (tb / "tb_spi_sc.v").write_text("x")
    assert default_human_tb(g, "spi") == tb / "tb_spi_sc.v"
    assert default_human_tb(ROOT / "dut" / "spi" / "rtl", "spi") == TB


def test_run_debug_eval_dry_run은_dut_옵션으로_다른_카탈로그를_쓴다(capsys):
    """--dut spi는 bugs/spi/bugs.json을 읽고 SPI TB를 입력으로 잡는다 (호출 없음)."""
    from scripts import run_debug_eval as cli
    assert cli.main(["--dut", "spi", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DUT spi: 평가 대상 30개" in out and "tb_spi_sc.v" in out and "spi_sc_tb" in out


def test_run_eval은_sync_fifo가_아닌_DUT의_결과를_eval_접두와_섞지_않는다(tmp_path):
    """기준선 리포트가 runs/eval_*의 최신을 쓰므로, SPI 사람 TB 평가는 다른 접두의 폴더로 간다."""
    from types import SimpleNamespace
    from scripts.run_eval import resolve_run
    meta = {"dut": "spi", "golden_rtl": "dut/spi/rtl", "top": "spi_sc_tb"}
    _, _, top, out = resolve_run(SimpleNamespace(tb=None, tb_top=None, out=None, label=None), meta, ROOT)
    assert top == "spi_sc_tb" and out.name.startswith("dut_spi_eval_") and not out.name.startswith("eval_")
