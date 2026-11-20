import argparse

from core.analyzer import analyze
from sim.workdir import new_workdir
from sim.xsim import XsimSim


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--label", default="run")
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--sim-timeout", type=float, default=60.0)
    a = ap.parse_args()

    wd = new_workdir(a.runs_dir, a.label)
    run = XsimSim(sim_timeout=a.sim_timeout).run(a.files, a.top, str(wd))
    result = analyze(run)

    print("workdir   :", run.workdir)
    for s in run.steps:
        print(f"{s.name:6} rc={s.returncode} timed_out={s.timed_out} {s.duration_s:.1f}s")
    print("total     :", round(run.total_duration_s, 1), "s")

    print()
    stage = f" (stage: {result.failed_stage})" if result.failed_stage else ""
    print("status    :", result.status + stage)
    print("tb_verdict:", result.tb_verdict)
    finish = f"{result.finish_time_ps} ps" if result.finish_time_ps is not None else None
    print("finish    :", finish)
    print("vcd_path  :", result.vcd_path)

    if result.unanalyzed_files:
        print("unanalyzed:")
        for f in result.unanalyzed_files:
            print("  -", f)
    if result.errors:
        print("errors    :  (* = 주 원인)")
        for e in result.errors:
            mark = "*" if e.is_primary else " "
            loc = f" ({e.file}:{e.line})" if e.file else ""
            t = f" @{e.time_ps}ps" if e.time_ps is not None else ""
            print(f"  {mark} [{e.stage}] {e.severity} {e.code or '-'}: {e.message}{loc}{t}")


if __name__ == "__main__":
    main()