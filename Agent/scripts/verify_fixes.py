"""이미 끝난 Debug Agent 평가(예: v0d)의 수정안을 사후 검증한다. LLM을 부르지 않는다 (Vivado 시뮬레이션만).

  python -m scripts.verify_fixes --label v0d            # runs/dbgeval_v0d_* 중 가장 최근 폴더
  python -m scripts.verify_fixes --results runs/dbgeval_v0d_20261120_101010

각 케이스의 보고서(fix_proposal_ids)가 지목한 수정안을 버그 있는 RTL에 적용해 원본 사람 TB로 재시뮬레이션하고
골든 RTL과 비교한다. 원본 결과 파일은 바꾸지 않고 `<results>/fix_check.json`과 `reports/fix_check_<dut>_<label>.md`를 쓴다.
"""

import argparse
import json
import sys
from pathlib import Path

from core.bugs import apply_bug, load_catalog
from core.fix_verify import FIX_CATEGORIES, check_fix, make_sim_fn
from scripts.run_debug_eval import ROOT, latest_out


def main(argv: list | None = None, runner=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=str(ROOT / "bugs" / "sync_fifo" / "bugs.json"))
    ap.add_argument("--label", default="human", help="--results가 없을 때 가장 최근 runs/dbgeval_<label>_* 사용")
    ap.add_argument("--results", help="평가 결과 폴더 (cases/*.json이 있는 곳)")
    ap.add_argument("--tb", help="원본 TB (기본: 사람이 쓴 dut/sync_fifo/tb/tb_sync_fifo_sc.v)")
    ap.add_argument("--tb-top", help="TB top 모듈 (기본: 카탈로그의 top)")
    ap.add_argument("--report", help="마크다운 경로 (기본: reports/fix_check_<dut>_<label>.md)")
    a = ap.parse_args(argv)

    meta = json.loads(Path(a.catalog).read_text(encoding="utf-8"))
    bugs = {b.id: b for b in load_catalog(a.catalog)}
    res = Path(a.results) if a.results else latest_out(ROOT, a.label)
    # run_debug_eval은 케이스를 <결과 폴더>/work/cases에 저장한다 (직접 지정한 작업 폴더면 <폴더>/cases)
    cases_dir = next((d for d in ((res / "work" / "cases", res / "cases") if res else ()) if d.is_dir()), None)
    if cases_dir is None:
        print(f"케이스 폴더를 찾지 못했습니다: {res or f'runs/dbgeval_{a.label}_*'} (work/cases 또는 cases 필요)")
        return 2
    golden_dir = ROOT / meta["golden_rtl"]
    tb = Path(a.tb) if a.tb else golden_dir.parent / "tb" / "tb_sync_fifo_sc.v"
    tb_top = a.tb_top or meta["top"]
    if not tb.is_file():
        print(f"TB 파일이 없습니다: {tb}")
        return 2
    if runner is None:
        from core.evaluator import xsim_runner
        runner = xsim_runner()
    golden = {f"rtl/{p.name}": p.read_text(encoding="utf-8", errors="replace") for p in sorted(golden_dir.glob("*.v"))}

    work = res / "fix_check_work"
    rows, counts = [], {k: 0 for k in FIX_CATEGORIES}
    for cf in sorted(cases_dir.glob("*.json")):
        case = json.loads(cf.read_text(encoding="utf-8"))
        if case.get("outcome") != "evaluated" or case["bug_id"] not in bugs:
            continue
        run = case["run"]
        applied_dir = work / case["bug_id"] / "rtl"
        if applied_dir.exists():
            import shutil
            shutil.rmtree(work / case["bug_id"])
        applied = apply_bug(bugs[case["bug_id"]], golden_dir, applied_dir)
        buggy = {f"rtl/{p.name}": p.read_text(encoding="utf-8", errors="replace") for p in sorted(applied.rtl_dir.glob("*.v"))}
        fx = check_fix(run.get("report"), run.get("proposals", []), buggy, golden,
                       make_sim_fn(runner, [tb], tb_top, work / case["bug_id"] / "sim")).to_dict()
        counts[fx["category"]] += 1
        rows.append({"bug_id": case["bug_id"], "location": case["score"]["category"], "fix": fx})
        print(f"{case['bug_id']}: 위치 {case['score']['category']}, 수정안 {fx['category']}", flush=True)

    out = {"results": str(res), "n": len(rows), "categories": counts, "cases": rows}
    (res / "fix_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    L = [f"# 수정안 사후 검증: {meta['dut']} ({res.name})", "",
         "Agent 보고서가 지목한 수정안을 버그 있는 RTL에 적용해 원본 사람 TB로 재시뮬레이션했다. "
         "PASS는 TB가 못 잡는 오류가 없다는 뜻이지 수정이 맞다는 증명이 아니다. fixed_pass는 diff를 직접 확인한다.", "",
         "| 분류 | 개수 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in counts.items()] + ["",
         "| 버그 | 위치 분류 | 수정안 | 제안별 (id: 상태, 골든과 같음) |", "|---|---|---|---|"]
    for r in rows:
        det = ", ".join(f"{x['id']}: {x['status']}{', 골든' if x.get('equals_golden') else ''}" for x in r["fix"]["results"]) or "-"
        L.append(f"| {r['bug_id']} | {r['location']} | {r['fix']['category']} | {det} |")
    rp = Path(a.report) if a.report else ROOT / "reports" / f"fix_check_{meta['dut']}_{res.name}.md"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n수정안 {len(rows)}개 케이스: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"결과: {res / 'fix_check.json'}\n리포트: {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())