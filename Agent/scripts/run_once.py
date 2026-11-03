import argparse

from sim.workdir import new_workdir
from sim.xsim import XsimSim

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--label", default="run")
    ap.add_argument("--runs-dir", default="runs")
    a = ap.parse_args()

    wd = new_workdir(a.runs_dir, a.label)
    res = XsimSim().run(a.files, a.top, str(wd))

    print("workdir   :", res.workdir)
    for s in res.steps:
        print(f"{s.name:6} rc={s.returncode} timed_out={s.timed_out} {s.duration_s:.1f}s")
    print("stopped_at:", res.stopped_at)
    print("vcd_path  :", res.vcd_path)
    print("total     :", round(res.total_duration_s, 1), "s")
    for line in res.steps[-1].stdout.splitlines():   # 임시 확인용 (파싱은 Phase 2)
        if "$finish" in line:
            print(line)

if __name__ == "__main__":
    main()