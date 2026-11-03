import sys
import tempfile
from pathlib import Path

from sim.runner import run_tool

root = Path(__file__).resolve().parents[1] / "Manual_test"

if "--err" in sys.argv:
    mem = root / "runs" / "case_compile_err" / "src" / "fifo_mem_err1.v"
else:
    mem = root / "dut" / "fifo_mem.v"

files = [
    root / "dut" / "async_fifo.v",
    root / "dut" / "bin2gray.v",
    root / "dut" / "fifo_ctrl.v",
    mem,
    root / "dut" / "synchronizer.v",
    root / "tb" / "tb_async_fifo.v",
]

wd = Path(tempfile.mkdtemp(prefix="try_"))
(wd / "files.f").write_text("\n".join(f.as_posix() for f in files) + "\n")

r = run_tool("xvlog", ["-sv", "-f", "files.f"], cwd=str(wd))
print("returncode:", r.returncode)
print("duration  :", round(r.duration_s, 2), "s")
print("Analyzing :", r.stdout.count("Analyzing"))
print("ERROR 줄  :", [l for l in r.stdout.splitlines() if l.startswith("ERROR")])