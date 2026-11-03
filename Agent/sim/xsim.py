import time
from pathlib import Path

from core.models import RunResult
from sim.base import Simulator
from sim.runner import run_tool

_TCL_TEMPLATE = Path(__file__).parent / "templates" / "run.tcl.tmpl"

class XsimSim(Simulator):
    def __init__(
        self,
        compile_timeout: float = 60.0,
        elab_timeout: float = 120.0,
        sim_timeout: float = 60.0,
        snapshot: str = "snap",
        vcd_name: str = "dump.vcd",
        run_time: str = "all",
    ):
        self.compile_timeout = compile_timeout
        self.elab_timeout = elab_timeout
        self.sim_timeout = sim_timeout
        self.snapshot = snapshot
        self.vcd_name = vcd_name
        self.run_time = run_time

    def run(self, files: list[str], top: str, workdir: str) -> RunResult:
        # 1) 입력 검증: 소스가 없는 것은 DUT 에러가 아니라 호출 측 실수이므로 예외
        sources = []
        for f in files:
            p = Path(f).resolve()
            if not p.is_file():
                raise FileNotFoundError(f"소스 파일이 없습니다: {f}")
            sources.append(p)

        # 2) 새 workdir (이미 있으면 FileExistsError: 이전 xsim.dir 재사용 방지)
        wd = Path(workdir).resolve()
        wd.mkdir(parents=True, exist_ok=False)

        # 3) files.f, run.tcl 생성 (UTF-8, BOM 없음)
        (wd / "files.f").write_text(
            "\n".join(p.as_posix() for p in sources) + "\n", encoding="utf-8"
        )
        tcl = _TCL_TEMPLATE.read_text(encoding="utf-8").format(
            vcd_name=self.vcd_name, run_time=self.run_time
        )
        (wd / "run.tcl").write_text(tcl, encoding="utf-8")

        # 4) 세 단계 실행
        steps = [
            ("xvlog", ["-sv", "-f", "files.f"], self.compile_timeout),
            ("xelab", ["-debug", "typical", top, "-s", self.snapshot], self.elab_timeout),
            ("xsim", [self.snapshot, "-tclbatch", "run.tcl", "-log", "sim.log"], self.sim_timeout),
        ]

        result = RunResult(workdir=str(wd))
        t0 = time.perf_counter()
        for name, args, tmo in steps:
            r = run_tool(name, args, cwd=str(wd), timeout=tmo)
            result.steps.append(r)
            if r.timed_out or r.returncode != 0:
                result.stopped_at = name      # 중단 정책: 다음 단계는 실행하지 않음
                break

        vcd = wd / self.vcd_name
        if vcd.exists():
            result.vcd_path = str(vcd)
        result.total_duration_s = time.perf_counter() - t0
        return result