"""Phase 7-4: run_debug_eval CLI (Vivado/Gemini 대신 가짜를 주입).

확인 사항: dry-run은 아무것도 호출하지 않는다 / 실행하면 결과 파일과 리포트가 만들어진다 /
한도로 멈추면 종료 코드 3과 이어하기 안내 / --resume은 가장 최근 폴더를 찾는다.
"""

import json

import pytest

from core.evaluator import Judged
from llm import DailyQuotaExceeded, FakeLLM, LLMClient
from scripts import run_debug_eval as cli

GOLDEN = "module a(input x, output y);\n  assign y = x;\nendmodule\n"
FAIL_LOG = "CHECK_FAIL t=27 ns sig=y exp=1 got=0\nCHECKS total=10 mismatches=1\n[TB] FAIL: 1\n"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    g = tmp_path / "dut" / "rtl"
    g.mkdir(parents=True)
    (g / "a.v").write_text(GOLDEN)
    (g.parent / "tb").mkdir()
    (g.parent / "tb" / "tb_sync_fifo_sc.v").write_text("module tb;\nendmodule\n")
    (g.parent / "spec.md").write_text("SPEC: y follows x\n")
    cat = tmp_path / "bugs.json"
    cat.write_text(json.dumps({"dut": "dut", "golden_rtl": str(g), "top": "tb", "bugs": [
        {"id": "B01_x", "dut": "dut", "type": "pointer", "file": "a.v", "find": "assign y = x;",
         "replace": "assign y = ~x;", "expect_count": 1, "description": "d", "equivalent": False},
        {"id": "E01_x", "dut": "dut", "type": "pointer", "file": "a.v", "find": "module a",
         "replace": "module  a", "expect_count": 1, "description": "d", "equivalent": True}]}), encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    calls = {"sim": 0, "make_client": 0}

    def runner(files, top, workdir):
        calls["sim"] += 1
        return Judged("FAIL", "FAIL", FAIL_LOG, 0.1, workdir, None)

    monkeypatch.setattr(cli, "xsim_runner", lambda: runner)
    return tmp_path, cat, calls


def tool(name, **a):
    return json.dumps({"thought": "t", "action": "tool", "tool": name, "args": a})


def final(line):
    rep = {"verdict": "rtl_bug", "location": {"file": "rtl/a.v", "line": line}, "summary": "s", "root_cause": "c",
           "evidence": [{"step": 1, "observation": "o"}], "fix_proposal_ids": [], "confidence": "high"}
    return json.dumps({"thought": "d", "action": "final", "report": rep})


def install_client(monkeypatch, calls, responses):
    fake = FakeLLM(responses)

    def mk(use_cache=True):
        calls["make_client"] += 1
        return LLMClient(fake)

    monkeypatch.setattr(cli, "make_client", mk)
    return fake


def test_dry_run은_아무것도_호출하지_않는다(setup, monkeypatch, capsys):
    """계획과 예상 호출 수만 출력한다. Vivado도 LLM 클라이언트 생성도 하지 않는다."""
    tmp, cat, calls = setup
    install_client(monkeypatch, calls, [])
    assert cli.main(["--catalog", str(cat), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "평가 대상 1개" in out and "동등 변형 1개 제외" in out and "예상 LLM 호출: 약 6회" in out
    assert "spec 사용" in out and calls == {"sim": 0, "make_client": 0}


def test_실행하면_결과와_리포트가_만들어진다(setup, monkeypatch, capsys):
    """정답 줄(1번 줄이 아니라 패치된 2번 줄)을 맞히면 정확한 줄 100%, 결과 JSON과 마크다운이 저장된다."""
    tmp, cat, calls = setup
    install_client(monkeypatch, calls, [tool("read_rtl", file="rtl/a.v"), final(2)])
    out_dir, report = tmp / "o", tmp / "r.md"
    assert cli.main(["--catalog", str(cat), "--out", str(out_dir), "--report", str(report)]) == 0
    d = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    assert d["summary"]["exact_rate"] == 1.0 and d["meta"]["label"] == "human"
    assert "정확한 줄" in report.read_text(encoding="utf-8")
    assert "정확한 줄 100%" in capsys.readouterr().out


def test_한도로_멈추면_종료코드3과_안내(setup, monkeypatch, capsys):
    """quota로 끝나면 종료 코드 3, 그리고 --resume 안내를 출력한다. 지금까지의 결과 파일은 남는다."""
    tmp, cat, calls = setup
    install_client(monkeypatch, calls, [DailyQuotaExceeded("일일 한도")])
    assert cli.main(["--catalog", str(cat), "--out", str(tmp / "o"), "--report", str(tmp / "r.md")]) == 3
    assert "--resume" in capsys.readouterr().out
    assert (tmp / "o" / "results.json").is_file() and (tmp / "o" / "work" / "cases" / "B01_x.json").is_file()


def test_resume은_가장_최근_폴더를_찾는다(setup, monkeypatch, capsys):
    """--out 없이 --resume을 주면 runs/dbgeval_<label>_* 중 가장 최근 폴더에서 이어간다. 없으면 종료 코드 2."""
    tmp, cat, calls = setup
    install_client(monkeypatch, calls, [])
    assert cli.main(["--catalog", str(cat), "--resume", "--report", str(tmp / "r.md")]) == 2
    assert "이어갈 폴더가 없습니다" in capsys.readouterr().out
    old = tmp / "runs" / "dbgeval_human_20260101_000000"
    new = tmp / "runs" / "dbgeval_human_20260202_000000"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    assert cli.latest_out(tmp, "human") == new


def test_LLM_설정_오류는_종료코드2(setup, monkeypatch, capsys):
    """키나 모델 설정이 없으면 Vivado를 돌리기 전에 안내하고 끝낸다."""
    tmp, cat, calls = setup

    def bad(use_cache=True):
        raise cli.ConfigError("RVA_LLM_MODEL이 없음")

    monkeypatch.setattr(cli, "make_client", bad)
    assert cli.main(["--catalog", str(cat), "--out", str(tmp / "o")]) == 2
    assert "LLM 설정 오류" in capsys.readouterr().out and calls["sim"] == 0


def test_only와_no_spec(setup, monkeypatch, capsys):
    """--only로 고르면 대상이 줄고, --no-spec이면 spec을 쓰지 않는다고 표시한다."""
    tmp, cat, calls = setup
    install_client(monkeypatch, calls, [])
    assert cli.main(["--catalog", str(cat), "--dry-run", "--no-spec", "--only", "ZZZ"]) == 0
    out = capsys.readouterr().out
    assert "평가 대상 0개" in out and "spec 미사용" in out