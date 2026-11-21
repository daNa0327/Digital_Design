"""평가 하네스: 골든 DUT와 버그 변형본을 일괄 실행해 TB의 버그 탐지 결과를 수집한다.

이 단계는 결정적 구간(실행, 로그 판정)만 쓴다. LLM/Agent 없이 "TB가 버그를 잡는가"를 먼저 잰다.
Agent 평가(원인 위치 정확도 등)는 같은 변형 세트와 정답 메타데이터를 그대로 재사용한다.

판정 규칙
- 골든이 PASS가 아니면 평가를 중단한다 (기준선이 깨지면 이후 수치는 의미가 없다).
- 일반 변형: FAIL이면 detected, PASS/NO_VERDICT이면 survived (TB가 못 잡음),
             COMPILE_ERROR/ELAB_ERROR/TIMEOUT이면 invalid (변형이 잘못 만들어짐 → 점수에서 제외하고 경고).
- 동등 변형: 생존이 정상(equivalent_ok), 잡히면 메타데이터 오류(equivalent_unexpected_detect).
- mutation score = detected / (detected + survived). invalid와 동등 변형은 분모에서 뺀다.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from core.bugs import Bug, apply_bug

_UNIT_PS = {"fs": 0.001, "ps": 1, "ns": 1_000, "us": 1_000_000, "ms": 1_000_000_000}
_CHECK_FAIL = re.compile(
    r"^CHECK_FAIL t=(?P<t>\d+)(?:\s*(?P<unit>fs|ps|ns|us|ms))?\s+sig=(?P<sig>\S+)\s+"
    r"exp=(?P<exp>\S+)\s+got=(?P<got>\S+)", re.M)
_CHECKS = re.compile(r"^CHECKS total=(?P<total>\d+) mismatches=(?P<mm>\d+)", re.M)


@dataclass
class Judged:
    """한 번 실행하고 판정한 결과 (실행기와 분리해서 하네스를 시뮬레이터 없이 테스트한다)."""
    status: str
    tb_verdict: str | None
    xsim_stdout: str
    duration_s: float
    workdir: str
    vcd_path: str | None = None


Runner = Callable[[list, str, str], Judged]     # (files, top, workdir) -> Judged


@dataclass
class CheckFail:
    t_ps: int | None
    signal: str
    expected: str
    got: str


def parse_check_fails(stdout: str) -> list[CheckFail]:
    """TB의 CHECK_FAIL 줄을 읽는다. 시각 단위가 없으면 t_ps는 None."""
    out = []
    for m in _CHECK_FAIL.finditer(stdout):
        unit = m.group("unit")
        t = int(int(m.group("t")) * _UNIT_PS[unit]) if unit else None
        out.append(CheckFail(t, m.group("sig"), m.group("exp"), m.group("got")))
    return out


def parse_checks(stdout: str) -> tuple[int | None, int | None]:
    m = _CHECKS.search(stdout)
    return (int(m.group("total")), int(m.group("mm"))) if m else (None, None)


@dataclass
class BugResult:
    bug_id: str
    type: str
    equivalent: bool
    outcome: str                  # detected | survived | invalid | equivalent_ok | equivalent_unexpected_detect
    status: str
    tb_verdict: str | None
    line: int | None
    first_fail_signal: str | None = None
    first_fail_time_ps: int | None = None
    n_mismatches: int | None = None
    total_checks: int | None = None
    duration_s: float = 0.0
    workdir: str = ""


@dataclass
class EvalReport:
    dut: str
    golden: dict
    aborted: bool
    results: list[BugResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"dut": self.dut, "golden": self.golden, "aborted": self.aborted,
                "summary": summarize(self.results), "results": [asdict(r) for r in self.results]}


def classify(bug: Bug, status: str) -> str:
    if status in ("COMPILE_ERROR", "ELAB_ERROR", "TIMEOUT"):
        return "invalid"
    detected = status == "FAIL"
    if bug.equivalent:
        return "equivalent_unexpected_detect" if detected else "equivalent_ok"
    return "detected" if detected else "survived"


def summarize(results: list[BugResult]) -> dict:
    c = Counter(r.outcome for r in results)
    scored = [r for r in results if r.outcome in ("detected", "survived")]
    det = c["detected"]
    by_type: dict[str, dict] = {}
    for r in scored:
        t = by_type.setdefault(r.type, {"detected": 0, "survived": 0})
        t[r.outcome] += 1
    return {
        "total": len(results),
        "detected": det,
        "survived": c["survived"],
        "invalid": c["invalid"],
        "equivalent_ok": c["equivalent_ok"],
        "equivalent_unexpected_detect": c["equivalent_unexpected_detect"],
        "mutation_score": (det / len(scored)) if scored else None,
        "by_type": by_type,
        "survivors": [r.bug_id for r in results if r.outcome == "survived"],
        "problems": [r.bug_id for r in results
                     if r.outcome in ("invalid", "equivalent_unexpected_detect")],
    }


def evaluate(bugs: list[Bug], golden_rtl_dir: str | Path, tb_path: str | Path, top: str,
             runner: Runner, work_root: str | Path, dut: str = "dut",
             progress: Callable[[str], None] | None = None) -> EvalReport:
    """골든을 먼저 돌리고, PASS일 때만 변형을 하나씩 실행한다."""
    say = progress or (lambda s: None)
    golden_dir, root = Path(golden_rtl_dir), Path(work_root)
    root.mkdir(parents=True, exist_ok=True)
    rtl_files = sorted(str(p) for p in golden_dir.glob("*.v"))

    say("golden 실행")
    g = runner(rtl_files + [str(tb_path)], top, str(root / "golden"))
    golden = {"status": g.status, "tb_verdict": g.tb_verdict, "duration_s": g.duration_s,
              "workdir": g.workdir}
    if not (g.status == "PASS" and g.tb_verdict == "PASS"):
        say("골든이 PASS가 아니라 평가를 중단합니다")
        return EvalReport(dut, golden, aborted=True)

    report = EvalReport(dut, golden, aborted=False)
    for i, bug in enumerate(bugs, 1):
        say(f"[{i}/{len(bugs)}] {bug.id}")
        applied = apply_bug(bug, golden_dir, root / bug.id / "rtl")
        files = sorted(str(p) for p in applied.rtl_dir.glob("*.v")) + [str(tb_path)]
        j = runner(files, top, str(root / bug.id / "run"))
        fails = parse_check_fails(j.xsim_stdout)
        total, mm = parse_checks(j.xsim_stdout)
        report.results.append(BugResult(
            bug_id=bug.id, type=bug.type, equivalent=bug.equivalent,
            outcome=classify(bug, j.status), status=j.status, tb_verdict=j.tb_verdict,
            line=applied.line,
            first_fail_signal=fails[0].signal if fails else None,
            first_fail_time_ps=fails[0].t_ps if fails else None,
            n_mismatches=mm, total_checks=total,
            duration_s=j.duration_s, workdir=j.workdir))
    return report


def xsim_runner() -> Runner:
    """실제 Vivado(XsimSim + analyze)로 실행하는 Runner. Vivado가 필요하다."""
    from core.analyzer import analyze
    from sim.xsim import XsimSim

    sim = XsimSim()

    def run(files: list, top: str, workdir: str) -> Judged:
        rr = sim.run(files, top, workdir)
        res = analyze(rr)
        xs = next((s.stdout for s in rr.steps if s.name == "xsim"), "")
        return Judged(res.status, res.tb_verdict, xs, rr.total_duration_s,
                      str(res.workdir), res.vcd_path)

    return run