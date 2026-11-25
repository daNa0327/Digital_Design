"""Phase 7-5: 수정안 검증 (재시뮬레이션).

질문: "Agent가 제안한 수정안을 적용하면 사람 TB가 PASS하는가? 골든 RTL과 같은가?"

- `make_sim_fn`: 수정안을 적용한 RTL({논리 이름: 텍스트})을 파일로 쓰고 Runner로 시뮬레이션하는 함수를 만든다.
  Agent의 `rerun_sim` 도구와 평가 하네스의 사후 검증이 같은 함수를 쓴다 (TB는 항상 원본 사람 TB).
- `check_fix`: 보고서가 지목한 수정안(fix_proposal_ids)을 버그 있는 RTL에 적용해 시뮬레이션하고 분류한다.

분류 (`FixResult.category`, 위에서부터 처음 해당하는 것)
  no_fix        보고서가 없거나 fix_proposal_ids가 비어 있음 (또는 저장된 제안과 맞지 않음)
  fixed_golden  PASS이고 수정 결과가 골든 RTL과 (주석/공백 제외) 같음 — 원래 코드로 되돌림
  fixed_pass    PASS이지만 골든과 다름 — 다른 올바른 수정일 수도, TB가 못 잡는 구멍일 수도 있음 (사람이 diff를 봐야 함)
  still_fail    시뮬레이션했지만 FAIL (또는 PASS가 아닌 상태)
  unverified    수정안을 적용하지 못했거나 시뮬레이션 자체가 실패함

주의: PASS는 "사람 TB가 못 잡는 오류가 없다"는 뜻이지 "수정이 맞다"의 증명이 아니다. 그래서 골든과의 일치를 따로 센다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.debug_tools import FixApplyError, apply_proposal
from core.evaluator import Judged, Runner, parse_check_fails, parse_checks
from core.rtl_analyzer import strip_comments

SimFn = Callable[[dict[str, str]], dict[str, Any]]
FIX_CATEGORIES = ("fixed_golden", "fixed_pass", "still_fail", "unverified", "no_fix")
MAX_FIRST_FAILURES = 3


def sim_summary(j: Judged) -> dict[str, Any]:
    """Judged를 Agent와 리포트가 읽는 작은 dict로 줄인다. 로그 전체는 주지 않는다."""
    fails = parse_check_fails(j.xsim_stdout or "")
    total, mm = parse_checks(j.xsim_stdout or "")
    first = [{"t_ps": f.t_ps, "signal": f.signal, "expected": f.expected, "got": f.got}
             for f in fails[:MAX_FIRST_FAILURES]]
    return {"status": j.status, "tb_verdict": j.tb_verdict, "n_check_fails": len(fails),
            "checks_total": total, "mismatches": mm, "first_failures": first}


def make_sim_fn(runner: Runner, tb_files: list[str | Path], tb_top: str, work_dir: str | Path) -> SimFn:
    """수정된 RTL로 시뮬레이션하는 함수. 호출마다 새 폴더(`sim1`, `sim2`, ...)를 쓴다 (xsim은 기존 폴더를 거부)."""
    root, n = Path(work_dir), [0]
    tbs = [str(t) for t in tb_files]

    def sim(rtl: dict[str, str]) -> dict[str, Any]:
        n[0] += 1
        d = root / f"sim{n[0]}"
        rtl_dir = d / "rtl"
        rtl_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for logical in sorted(rtl):
            p = rtl_dir / Path(logical).name
            p.write_text(rtl[logical], encoding="utf-8")
            paths.append(str(p))
        return sim_summary(runner(paths + tbs, tb_top, str(d / "run")))

    return sim


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", strip_comments(text))


def equals_golden(patched: dict[str, str], golden: dict[str, str]) -> bool:
    """수정된 RTL이 골든과 같은가 (주석과 공백 제외, 모든 파일)."""
    return set(patched) == set(golden) and all(_norm(patched[k]) == _norm(golden[k]) for k in golden)


@dataclass
class FixResult:
    category: str
    claimed_ids: list[int] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)     # 제안별: id, status, equals_golden, error

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "claimed_ids": self.claimed_ids, "results": self.results}


def check_fix(report: dict[str, Any] | None, proposals: list[dict[str, Any]], buggy_rtl: dict[str, str],
              golden_rtl: dict[str, str], sim: SimFn) -> FixResult:
    """보고서가 지목한 수정안을 각각 버그 있는 RTL에 적용해 시뮬레이션하고 분류한다."""
    ids = [i for i in (report or {}).get("fix_proposal_ids", []) if isinstance(i, int)]
    by_id = {p["id"]: p for p in proposals}
    ids = [i for i in dict.fromkeys(ids) if i in by_id]
    if not ids:
        return FixResult("no_fix")
    results: list[dict[str, Any]] = []
    for i in ids:
        p = by_id[i]
        r: dict[str, Any] = {"id": i, "file": p["file"], "line": p["line"]}
        try:
            patched = apply_proposal(buggy_rtl, p["file"], p["find"], p["replace"])
        except FixApplyError as e:
            r.update(status="apply_error", error=str(e))
            results.append(r)
            continue
        try:
            s = sim(patched)
        except Exception as e:                         # 시뮬레이터 실행 실패는 케이스를 죽이지 않고 unverified로 남긴다
            r.update(status="sim_error", error=f"{type(e).__name__}: {e}")
            results.append(r)
            continue
        r.update(status=s["status"], n_check_fails=s["n_check_fails"], equals_golden=equals_golden(patched, golden_rtl))
        results.append(r)
    passed = [r for r in results if r["status"] == "PASS"]
    if any(r["equals_golden"] for r in passed):
        cat = "fixed_golden"
    elif passed:
        cat = "fixed_pass"
    elif any(r["status"] not in ("apply_error", "sim_error") for r in results):
        cat = "still_fail"
    else:
        cat = "unverified"
    return FixResult(cat, ids, results)
