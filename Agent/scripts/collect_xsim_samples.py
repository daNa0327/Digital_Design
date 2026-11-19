# xsim 로그 샘플 수집 (일회성 도구). TB 끝부분만 바꾼 복사본을 돌려 실제 출력을 저장한다.
import re
from pathlib import Path

from sim.workdir import new_workdir
from sim.xsim import XsimSim

ROOT = Path(__file__).resolve().parents[1]
MT = ROOT / "Manual_test"
DUT = [
    str(MT / "dut" / n)
    for n in ("async_fifo.v", "bin2gray.v", "fifo_ctrl.v", "fifo_mem.v", "synchronizer.v")
]
TB = (MT / "tb" / "tb_async_fifo.v").read_text(encoding="utf-8", errors="replace")
OUT = ROOT / "tests" / "data"
VARIANTS = ROOT / "runs" / "_variants"
END = "#50; $finish;"

# 이름: (END를 대체할 코드, xsim 타임아웃 초)
CASES = {
    "pass_marker":     ('#50; $display("[TB] PASS"); $finish;', 60),
    "fail_marker":     ('#50; $display("[TB] FAIL: dummy check"); $finish;', 60),
    "error":           ('#50; $error("dummy error"); $finish;', 60),
    "fatal":           ('#50; $fatal(1, "dummy fatal"); $finish;', 60),
    "pass_with_error": ('#50; $error("dummy error"); $display("[TB] PASS"); $finish;', 60),
    "hang":            ("#50;", 10),    # $finish 없음 → 타임아웃
}
INTERESTING = re.compile(r"\[TB\]|error|fatal|\$finish|\$stop", re.I)


def norm(s: str) -> str:
    return s.replace("\r\n", "\n").strip()


def main() -> None:
    if END not in TB:
        raise SystemExit(f"TB에서 '{END}'를 찾지 못했습니다. TB 끝부분을 확인하세요.")
    VARIANTS.mkdir(parents=True, exist_ok=True)

    summary = []
    for name, (repl, sim_timeout) in CASES.items():
        tb_path = VARIANTS / f"tb_{name}.v"
        tb_path.write_text(TB.replace(END, repl), encoding="utf-8")

        wd = new_workdir(ROOT / "runs", f"sample_{name}")
        res = XsimSim(sim_timeout=sim_timeout).run(
            DUT + [str(tb_path)], "async_fifo_tb", str(wd)
        )
        step = res.steps[-1]

        print(f"\n===== {name} =====")
        print(f"last step: {step.name} rc={step.returncode} "
              f"timed_out={step.timed_out} stopped_at={res.stopped_at}")

        if step.name == "xsim":
            (OUT / f"xsim_{name}.log").write_text(step.stdout, encoding="utf-8")
            logfile = wd / "sim.log"
            same = logfile.exists() and norm(
                logfile.read_text(encoding="utf-8", errors="replace")
            ) == norm(step.stdout)
            print("sim.log == stdout:", same)

        for line in step.stdout.splitlines():
            if INTERESTING.search(line):
                print("  |", line)
        summary.append((name, step.name, step.returncode, step.timed_out))

    print("\n===== 요약 =====")
    for row in summary:
        print(row)


if __name__ == "__main__":
    main()