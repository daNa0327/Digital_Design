"""TB Generator 6-2: RTL 요약(summary)과 소스로 LLM 프롬프트를 만든다.

원칙: 코드가 이미 아는 사실(포트, 폭, 클럭/리셋, timescale 규칙)은 LLM이 추측하지 않게 프롬프트에
"사실"로 박아 넣고, LLM에게는 명세에서 기대 동작을 모델링하고 자극을 설계하는 일만 맡긴다.
출력 규약(`[TB] PASS/FAIL`, CHECK_FAIL, CHECKS)은 Phase 2 파서와 Phase 4 평가 하네스가 읽는 형식 그대로다.

공개 API:
    load_sources(summary, base=None) -> {경로: 텍스트}   # summary의 sha256과 대조해 낡은 요약을 거부
    build_tb_prompt(summary, sources, spec_text=None) -> (system, prompt)
    tb_module_name(summary) -> str
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.rtl_summary import validate_summary


class TBPromptError(Exception):
    """프롬프트를 만들 수 없는 요약/소스 (사람이 먼저 해결해야 함)."""


def tb_module_name(summary: dict) -> str:
    return f"tb_{summary['top']}"


# ---------------------------------------------------------------- 소스 읽기
def load_sources(summary: dict, base: str | Path | None = None) -> dict[str, str]:
    """summary.sources의 파일을 읽는다. 내용 해시가 요약과 다르면 거부한다 (요약 이후 RTL이 바뀐 경우)."""
    root = Path(base) if base else Path(".")
    out: dict[str, str] = {}
    for s in summary["sources"]:
        p = root / s["path"]
        if not p.is_file():
            raise TBPromptError(f"소스 파일이 없음: {p}")
        raw = p.read_bytes()
        if hashlib.sha256(raw).hexdigest()[:12] != s["sha256"]:
            raise TBPromptError(f"요약을 만든 뒤 RTL이 바뀜: {s['path']} - 요약을 다시 만드세요")
        # 해시는 원본 바이트로 검증하고, 프롬프트용 텍스트는 줄바꿈을 \n으로 통일한다
        # (OS마다 프롬프트와 캐시 키가 달라지는 것을 막음)
        out[s["path"]] = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return out


# ---------------------------------------------------------------- 프롬프트 조각
SYSTEM = """\
You are a senior digital design verification engineer. You write self-checking Verilog-2001 testbenches \
that are run by an automated flow (Vivado xsim) and judged only by what they print. \
Follow the output contract exactly: a testbench that does not follow it is rejected by a script before it is ever simulated. \
Never invent ports, widths or clocks: the FACTS section is authoritative."""


def _clock_rules(summary: dict) -> list[str]:
    rules = []
    clocks = summary["clocks"]
    if not clocks:
        rules.append("The DUT has no clock port: treat it as combinational. Apply inputs, wait a short delay, then compare.")
        return rules
    periods = [10, 14, 22, 26]
    for i, c in enumerate(clocks):
        per = periods[i % len(periods)]
        rules.append(f"Clock `{c['port']}`: initialize to 0 and generate it with `always #{per // 2} {c['port']} = ~{c['port']};` "
                     f"(period {per} time units).")
    if summary["multi_clock"]:
        rules.append("Several clocks exist: each is an independent generator with a different, unrelated period. "
                     "Treat every output as belonging to the clock domain that produces it and compare it against that domain's own edge.")
    return rules


def _reset_rules(summary: dict) -> list[str]:
    rules = []
    for r in summary["resets"]:
        pol = "active-high (1 = reset)" if r["active_high"] else "active-low (0 = reset)"
        kind = "asynchronous" if r["asynchronous"] else "synchronous"
        rules.append(f"Reset `{r['port']}`: {pol}, {kind}. Initialize it to the INACTIVE value, apply it at the start "
                     "and again in the middle of operation with data in the DUT, and do not compare outputs before the first reset has finished.")
    if not summary["resets"]:
        rules.append("No reset was found: do not invent one. Initialize inputs explicitly and compare only values the spec defines.")
    return rules


def _timescale_rule(summary: dict) -> str:
    d = summary["timescale"]["tb_directive"]
    if d == "":
        return ("Do NOT write any `timescale directive. The RTL has none, and mixing a timescaled TB with untimescaled RTL "
                "makes xelab fail (XSIM 43-4099). The default unit is 1 ns, so `#5` is 5 ns.")
    return (f'Every RTL module already has a timescale, so the testbench must have the same one. '
            f'The first non-comment line of the file must be exactly: {d}')


def _facts(summary: dict) -> dict:
    keep = ("top", "ports", "inputs_to_drive", "outputs_to_observe", "parameters", "clocks", "resets",
            "multi_clock", "notes")
    f = {k: summary[k] for k in keep}
    f["ports"] = [{"name": p["name"], "direction": p["direction"], "width": p["width"]} for p in summary["ports"]]
    return f


def _contract(summary: dict) -> str:
    top, tb = summary["top"], tb_module_name(summary)
    clock_rules = "\n".join(f"  - {r}" for r in _clock_rules(summary))
    reset_rules = "\n".join(f"  - {r}" for r in _reset_rules(summary))
    return f"""\
OUTPUT CONTRACT (all items are mandatory)
1. Reply with exactly ONE fenced code block (```verilog ... ```) and nothing else outside it.
2. The block holds ONE module named `{tb}` with no ports. Verilog-2001 only: no `logic`, `always_ff`, `int`, `bit`, \
classes, `$urandom`, assertions or any other SystemVerilog.
3. Instantiate the DUT as `{top} dut (...)` with named port connections `.port(signal)` covering EVERY port, \
using TB signals named exactly like the ports.
4. Timescale: {_timescale_rule(summary)}
5. Clocks and resets:
{clock_rules}
{reset_rules}
6. Race-free timing: change inputs on the falling edge of the primary clock; sample and compare outputs a short delay \
(2 time units) after the active clock edge, before the next input change. Never drive inputs on the sampling edge.
7. Self-checking: write a behavioral reference model from the SPEC, driven by the same inputs, and compare ONLY the DUT's \
top-level ports with `!==` (so X and Z are mismatches). Do not read DUT internal signals. \
Enable comparisons only after the first reset has finished.
8. Log protocol (parsed by scripts, keep the exact text):
   - for each mismatch, at most 10 times: `$display("CHECK_FAIL t=%0t sig=<port name> exp=%0h got=%0h", $time, exp, got);`
   - once at the end: `$display("CHECKS total=%0d mismatches=%0d", checks, errors);` where `checks` counts clock cycles compared
   - then exactly one of `$display("[TB] PASS");` (errors == 0) or `$display("[TB] FAIL: %0d mismatches", errors);`
   - the prefix `[TB]` is reserved for those two lines; never print it anywhere else.
9. Always finish with `$finish`. Add a watchdog near the top: `initial begin #<generous limit>; \
$display("[TB] FAIL: timeout"); $finish; end`.
10. Forbidden: `$stop`, `$fatal`, `$error`, `$dumpfile`, `$dumpvars` (waveforms are recorded by the flow), file I/O, `force`/`release`.
11. Stimulus must be deterministic: fixed seed, `$random(seed)` only.
12. Stimulus plan (cover each that applies to this DUT): reset behaviour; every boundary condition named in the SPEC; \
back-to-back operations; simultaneous opposite operations at each boundary; reset while the DUT holds state and recovery after it; \
a long constrained-random phase (a few thousand cycles) split into phases with different input probabilities; \
data patterns that expose stuck or swapped bits (all zeros, all ones, walking one, random). \
Count how often each boundary was actually reached and print one `COVER ...` line before `CHECKS`.
13. Short comments are welcome. Put any assumption you had to make about unclear behaviour in a comment block \
that starts with `// ASSUMPTIONS:` at the top of the module."""


# ---------------------------------------------------------------- 공개 API
def build_tb_prompt(summary: dict, sources: dict[str, str], spec_text: str | None = None) -> tuple[str, str]:
    """(system, prompt)를 만든다. 요약이 TB를 만들 수 없는 상태면 TBPromptError."""
    bad = validate_summary(summary)
    if bad:
        raise TBPromptError(f"요약이 스키마에 맞지 않음: {bad}")
    if not summary["ready_for_tb"]:
        raise TBPromptError("TB를 만들 수 없는 요약 (blockers): " + "; ".join(summary["blockers"]))
    if not sources:
        raise TBPromptError("RTL 소스가 비어 있음")

    parts = ["Write a self-checking testbench for the DUT described below.\n",
             "## FACTS (extracted by a deterministic parser; authoritative)",
             "```json", json.dumps(_facts(summary), ensure_ascii=False, indent=1), "```\n",
             "## DUT SOURCE"]
    for path, text in sources.items():
        parts += [f"### {Path(path).name}", "```verilog", text.rstrip(), "```"]
    parts.append("")
    if spec_text and spec_text.strip():
        parts += ["## SPEC (intended behaviour; the reference model must follow this)", spec_text.strip(), ""]
    else:
        parts += ["## SPEC",
                  "No separate specification was given. Derive the intended behaviour from the DUT source and the facts, "
                  "model that behaviour independently in the testbench, and list every assumption under `// ASSUMPTIONS:`.\n"]
    parts.append(_contract(summary))
    return SYSTEM, "\n".join(parts)