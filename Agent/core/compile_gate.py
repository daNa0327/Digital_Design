"""TB Generator 6-3: Compile Gate. TB 코드가 시뮬레이션 전에 컴파일/엘라보레이션되는지 결정적으로 확인한다.

정적 검사(tb_check)는 규약만 본다. 문법, 선언 위치, 모듈/포트 해석은 도구만 알 수 있어서
`xvlog`(문법) -> `xelab`(엘라보레이션: 모듈 연결, 포트, timescale)까지 돌려 본다. xsim(시뮬레이션)은 돌리지 않는다.

모드: 기본은 Verilog 모드(`-sv` 없음). 프롬프트 계약이 Verilog-2001이고 v1 범위도 Verilog라서,
`-sv`로는 통과하지만 순수 Verilog에서는 안 되는 코드(예: 이름 없는 블록 안의 선언)를 여기서 걸러낸다.
`sv=True`로 평가 흐름(`xvlog -sv`)과 같은 조건으로도 돌릴 수 있다.

공개 API:
    compile_check(rtl_files, tb_code, tb_top, work_root, sv=False, ...) -> CompileResult
    parse_compile_errors(stdout, stage) -> list[CompileError]
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from core.rtl_analyzer import strip_comments
from sim.runner import run_tool

# `ERROR: [VRFC 10-8885] 메시지 [C:/경로/파일.v:103]`   (경로 부분은 없을 수도 있음)
_ERROR_LINE = re.compile(
    r"^ERROR:\s*\[(?P<code>[A-Za-z]+\s[\d-]+)\]\s*(?P<msg>.*?)(?:\s*\[(?P<file>.+?):(?P<line>\d+)\])?\s*$", re.M)
# 앞선 에러의 결과로 따라 나오는 줄 (원인이 아니라서 되먹임에서 뺀다)
_DERIVED = ("is ignored due to previous errors", "Static elaboration of top level", "Please see the previously")


@dataclass
class CompileError:
    stage: str                      # "xvlog" | "xelab"
    code: str | None                # 예: "VRFC 10-8885"
    message: str
    file: str | None = None
    line: int | None = None
    primary: bool = True            # False면 앞선 에러의 파생 메시지

    def __str__(self) -> str:
        loc = f" ({Path(self.file).name}:{self.line})" if self.file and self.line else ""
        return f"[{self.stage}] {self.code or '?'}: {self.message}{loc}"


@dataclass
class CompileResult:
    ok: bool
    stage: str | None                       # 실패한 단계 ("xvlog" | "xelab"), 성공이면 None
    errors: list[CompileError] = field(default_factory=list)
    stdout: str = ""                        # 실패한 단계의 원본 출력
    workdir: str = ""
    sv: bool = False
    timed_out: bool = False
    duration_s: float = 0.0
    tb_file: str = ""

    def primary_errors(self) -> list[CompileError]:
        """파생 메시지를 뺀 원인 에러 (모두 파생이면 전체)."""
        prim = [e for e in self.errors if e.primary]
        return prim or self.errors


def parse_compile_errors(stdout: str, stage: str) -> list[CompileError]:
    """xvlog/xelab 출력에서 ERROR 줄을 뽑는다. 파생 메시지는 primary=False로 표시한다."""
    out = []
    for m in _ERROR_LINE.finditer(stdout):
        msg = m.group("msg").strip()
        out.append(CompileError(
            stage=stage, code=m.group("code"), message=msg, file=m.group("file"),
            line=int(m.group("line")) if m.group("line") else None,
            primary=not any(d in msg for d in _DERIVED)))
    return out


def tb_top_of(code: str) -> str | None:
    """코드의 첫 module 이름 (xelab의 top으로 씀)."""
    m = re.search(r"(?m)^\s*module\s+(\w+)", strip_comments(code))    # 주석이나 문장 속 'module' 단어는 제외
    return m.group(1) if m else None


def _run(name: str, args: list[str], cwd: Path, timeout: float, stage: str):
    r = run_tool(name, args, cwd=str(cwd), timeout=timeout)
    errs = parse_compile_errors(r.stdout, stage)
    failed = bool(getattr(r, "timed_out", False)) or r.returncode != 0 or any(e.primary for e in errs)
    return r, errs, failed


def compile_check(rtl_files: list[str | Path], tb_code: str, tb_top: str | None, work_root: str | Path,
                  sv: bool = False, xvlog_timeout: float = 60, xelab_timeout: float = 120) -> CompileResult:
    """RTL과 TB 코드를 새 임시 폴더(work_root 아래)에서 xvlog -> xelab으로 확인한다.

    TB는 `tb_code` 그대로(머리말 주석 없이) 파일로 써서, 에러 줄 번호가 LLM이 본 코드의 줄 번호와 같다.
    도구가 PATH에 없으면 FileNotFoundError (TB 문제가 아니라 환경 문제이므로 결과로 돌려주지 않음).
    """
    top = tb_top or tb_top_of(tb_code)
    if not top:
        return CompileResult(ok=False, stage="xvlog", sv=sv, errors=[
            CompileError("xvlog", None, "TB 코드에서 module 이름을 찾지 못함")])
    root = Path(work_root)
    root.mkdir(parents=True, exist_ok=True)
    wd = Path(tempfile.mkdtemp(prefix="gate_", dir=root))
    tb_file = wd / f"{top}.v"
    tb_file.write_text(tb_code, encoding="utf-8")
    files = [str(Path(f).resolve()) for f in rtl_files] + [str(tb_file)]

    total = 0.0
    r, errs, failed = _run("xvlog", (["-sv"] if sv else []) + files, wd, xvlog_timeout, "xvlog")
    total += r.duration_s
    stage = "xvlog"
    if not failed:
        r, errs, failed = _run("xelab", [top, "-s", "gate_snap"], wd, xelab_timeout, "xelab")
        total += r.duration_s
        stage = "xelab"
    if not failed:
        return CompileResult(ok=True, stage=None, workdir=str(wd), sv=sv, duration_s=total, tb_file=str(tb_file))

    timed_out = bool(getattr(r, "timed_out", False))
    if timed_out:
        errs = errs + [CompileError(stage, "TIMEOUT", f"{stage}이 제한 시간 안에 끝나지 않음")]
    elif not errs:
        errs = [CompileError(stage, None, f"{stage} 종료 코드 {r.returncode} (ERROR 줄 없음)")]
    return CompileResult(ok=False, stage=stage, errors=errs, stdout=r.stdout, workdir=str(wd), sv=sv,
                         timed_out=timed_out, duration_s=total, tb_file=str(tb_file))