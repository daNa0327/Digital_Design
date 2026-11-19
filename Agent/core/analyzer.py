import os

from core.log_parser import parse_xelab, parse_xsim, parse_xvlog
from core.models import ErrorItem, RunResult, SimResult


def _norm(path: str) -> str:
    """구분자(/ vs \\)와 대소문자 차이를 없애서 경로를 비교한다 (Windows 기준)."""
    return os.path.normcase(os.path.normpath(path))


def _synthetic(stage: str, code: str, message: str, primary: bool) -> ErrorItem:
    return ErrorItem(stage=stage, code=code, message=message, is_primary=primary)


def _finish(res: SimResult, status: str, stage: str) -> SimResult:
    res.status = status
    res.failed_stage = stage
    return res


def analyze(run: RunResult) -> SimResult:
    if not run.steps:
        raise ValueError("RunResult.steps가 비어 있습니다")

    steps = {s.name: s for s in run.steps}
    res = SimResult(status="NO_VERDICT", workdir=run.workdir, vcd_path=run.vcd_path)

    # ---- 1. xvlog -------------------------------------------------
    s = steps.get("xvlog")
    if s is not None:
        info = parse_xvlog(s.stdout)
        res.errors += info.errors
        attempted = {_norm(p) for p in info.attempted_files}
        res.unanalyzed_files = [f for f in run.sources if _norm(f) not in attempted]
        if s.timed_out:
            return _finish(res, "TIMEOUT", "xvlog")
        if s.returncode != 0 or info.errors:
            if not info.errors:
                res.errors.append(_synthetic(
                    "xvlog", "EXIT_CODE",
                    f"xvlog exited with code {s.returncode} but no ERROR line was found",
                    primary=True))
            return _finish(res, "COMPILE_ERROR", "xvlog")

    # ---- 2. xelab -------------------------------------------------
    s = steps.get("xelab")
    if s is not None:
        info = parse_xelab(s.stdout)
        res.errors += info.errors
        if s.timed_out:
            return _finish(res, "TIMEOUT", "xelab")
        if s.returncode != 0 or info.errors or not info.snapshot_built:
            if not info.errors:
                if s.returncode != 0:
                    code = "EXIT_CODE"
                    msg = f"xelab exited with code {s.returncode} but no ERROR line was found"
                else:
                    code = "NO_SNAPSHOT"
                    msg = "xelab finished without building a simulation snapshot"
                res.errors.append(_synthetic("xelab", code, msg, primary=True))
            return _finish(res, "ELAB_ERROR", "xelab")

    # ---- 3. xsim --------------------------------------------------
    s = steps.get("xsim")
    if s is None:
        raise ValueError("xvlog/xelab은 성공했는데 xsim 단계 기록이 없습니다")

    info = parse_xsim(s.stdout)
    res.errors += info.errors
    res.finish_time_ps = info.finish_time_ps

    verdicts = [v for v, _ in info.tb_markers]
    if "FAIL" in verdicts:
        res.tb_verdict = "FAIL"
    elif "PASS" in verdicts:
        res.tb_verdict = "PASS"

    if s.timed_out:
        return _finish(res, "TIMEOUT", "xsim")

    # [TB] FAIL 마커를 에러 목록에 합쳐서 "무엇이 실패했는지"를 한 곳에서 볼 수 있게 한다
    tb_fails = [
        ErrorItem(stage="xsim", code="TB_FAIL", message=msg or "[TB] FAIL")
        for v, msg in info.tb_markers if v == "FAIL"
    ]
    if tb_fails and not info.errors:
        tb_fails[0].is_primary = True
    res.errors += tb_fails

    if s.returncode != 0:
        res.errors.append(_synthetic(
            "xsim", "EXIT_CODE",
            f"xsim exited with code {s.returncode}",
            primary=not any(e.stage == "xsim" for e in res.errors)))

    if any(e.stage == "xsim" for e in res.errors):
        return _finish(res, "FAIL", "xsim")

    res.status = "PASS" if res.tb_verdict == "PASS" else "NO_VERDICT"
    return res