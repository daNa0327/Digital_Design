import tempfile
from pathlib import Path

from sim.runner import run_tool

root = Path(__file__).resolve().parents[1] / "Manual_test"
wd = Path(tempfile.mkdtemp(prefix="hang_"))

# $finish를 주석 처리한 TB 복사본 (원본 TB는 수정하지 않음)
tb = (root / "tb" / "tb_async_fifo.v").read_text(encoding="utf-8", errors="replace")
(wd / "tb_hang.v").write_text(tb.replace("$finish;", "// $finish;"), encoding="utf-8")

names = ["async_fifo.v", "bin2gray.v", "fifo_ctrl.v", "fifo_mem.v", "synchronizer.v"]
files = [root / "dut" / n for n in names] + [wd / "tb_hang.v"]
(wd / "files.f").write_text("\n".join(f.as_posix() for f in files) + "\n")

steps = [
    ("xvlog", ["-sv", "-f", "files.f"], 60),
    ("xelab", ["-debug", "typical", "async_fifo_tb", "-s", "snap"], 60),
    ("xsim",  ["snap", "-runall", "-log", "sim.log"], 10),
]

for name, args, tmo in steps:
    r = run_tool(name, args, cwd=str(wd), timeout=tmo)
    print(f"{name:6} rc={r.returncode} timed_out={r.timed_out} {r.duration_s:.1f}s")
    if r.returncode != 0:      # 타임아웃(None)이나 에러면 중단
        break

print("workdir:", wd)
print(r.stdout[-300:])