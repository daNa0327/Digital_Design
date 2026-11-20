"""VCD 파일 읽기 (시뮬레이터 무관).

핵심 규칙
- 값 이력은 이름이 아니라 **VCD 식별자(ID) 기준**으로 저장한다.
  같은 ID를 여러 계층 이름이 공유할 수 있다(alias). 이름 기준으로 저장하면 덮어써진다.
- VCD는 값이 **바뀔 때만** 기록한다. value_at(t)는 "t 이하의 마지막 변화값"이다.
- end_time_ps는 마지막 타임스탬프일 뿐, 시뮬레이션 종료 시각이 아니다 (종료 시각은 로그의 $finish).
- 파일 끝이 줄바꿈으로 끝나지 않으면(타임아웃으로 죽은 xsim 등) 마지막 줄은 잘렸다고 보고 버린다.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

_UNIT_PS = {"s": 10**12, "ms": 10**9, "us": 10**6, "ns": 10**3, "ps": 1}
_IGNORED = {"$dumpvars", "$dumpall", "$dumpon", "$dumpoff", "$end", "$comment"}


@dataclass(frozen=True)
class VcdSignal:
    name: str    # 전체 계층 이름 (예: tb.dut.wr_ck)
    id: str      # VCD 식별자
    width: int
    kind: str    # wire, reg 등


class VcdReader:
    def __init__(self) -> None:
        self.timescale_ps: int = 1
        self.end_time_ps: int = 0
        self._signals: dict[str, VcdSignal] = {}          # 이름 -> 신호
        self._id_names: dict[str, list[str]] = {}         # ID -> 이름들
        self._times: dict[str, list[int]] = {}            # ID -> 변화 시각(ps)
        self._values: dict[str, list[str]] = {}           # ID -> 변화값
        self._keep: set[str] | None = None                # 적재할 ID (None이면 전부)
        self._until_ps: int | None = None                 # 이 시각 이후는 읽지 않음
        self._signal_filter: list[str] | None = None

    # ---------- 생성 ----------
    @classmethod
    def from_file(cls, path: str | Path, signals: list[str] | None = None,
                  until_ps: int | None = None) -> "VcdReader":
        """signals: 적재할 신호 이름 목록(alias는 같은 ID라 함께 적재됨). until_ps: 이 시각까지만 읽음."""
        r = cls()
        r._signal_filter, r._until_ps = signals, until_ps
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            r._parse(f)
        return r

    @classmethod
    def from_text(cls, text: str, signals: list[str] | None = None,
                  until_ps: int | None = None) -> "VcdReader":
        r = cls()
        r._signal_filter, r._until_ps = signals, until_ps
        r._parse(text.splitlines(keepends=True))
        return r

    # ---------- 조회 ----------
    def names(self) -> list[str]:
        return list(self._signals)

    def find(self, substr: str) -> list[str]:
        return [n for n in self._signals if substr in n]

    def info(self, name: str) -> VcdSignal:
        try:
            return self._signals[name]
        except KeyError:
            raise KeyError(f"VCD에 없는 신호: {name!r} (find()로 이름을 찾으세요)") from None

    def aliases(self, name: str) -> list[str]:
        """같은 ID를 공유하는 다른 이름들 (자기 자신 제외)."""
        sig = self.info(name)
        return [n for n in self._id_names[sig.id] if n != name]

    def _loaded(self, sig: VcdSignal) -> None:
        if self._keep is not None and sig.id not in self._keep:
            raise ValueError(f"{sig.name!r}는 signals 필터에 없어 적재되지 않았습니다")

    def changes(self, name: str) -> list[tuple[int, str]]:
        sig = self.info(name)
        self._loaded(sig)
        return list(zip(self._times.get(sig.id, []), self._values.get(sig.id, [])))

    def value_at(self, name: str, t_ps: int) -> str | None:
        """t_ps 이하의 마지막 변화값. 첫 변화보다 이르면 None."""
        sig = self.info(name)
        self._loaded(sig)
        times = self._times.get(sig.id, [])
        i = bisect_right(times, t_ps)
        return self._values[sig.id][i - 1] if i else None

    def window(self, name: str, t0_ps: int, t1_ps: int,
               include_initial: bool = True) -> list[tuple[int, str]]:
        """[t0, t1] 구간의 변화. include_initial이면 t0 시점의 값을 (t0, 값)으로 앞에 붙인다."""
        out = [(t, v) for t, v in self.changes(name) if t0_ps <= t <= t1_ps]
        if include_initial and not (out and out[0][0] == t0_ps):
            v0 = self.value_at(name, t0_ps)
            if v0 is not None:
                out.insert(0, (t0_ps, v0))
        return out

    def net_group(self, name: str, min_changes: int = 2,
                  same_leaf: bool = True) -> dict[str, list[str]]:
        """같은 net일 가능성이 있는 다른 이름들.

        alias      : 같은 VCD ID를 공유 (확실히 같은 값)
        same_history: ID는 다르지만 폭과 변화 이력이 완전히 같음 (**후보**일 뿐, 같은 net이라는 증명은 아님)
        상수에 가까운 신호의 우연한 일치를 막으려고 기록(초기값 포함)이 min_changes건 미만이면 후보에서 제외하고,
        same_leaf=True이면 마지막 이름(wr_ck 등)이 같은 신호끼리만 비교한다.
        """
        sig = self.info(name)
        self._loaded(sig)
        mine = self.changes(name)
        cands: list[str] = []
        if len(mine) >= min_changes:
            leaf = name.rsplit(".", 1)[-1]
            for other, osig in self._signals.items():
                if osig.id == sig.id or osig.width != sig.width:
                    continue
                if same_leaf and other.rsplit(".", 1)[-1] != leaf:
                    continue
                if self._keep is not None and osig.id not in self._keep:
                    continue
                if self.changes(other) == mine:
                    cands.append(other)
        return {"alias": self.aliases(name), "same_history": cands}

    def status(self, name: str) -> tuple[str, str]:
        """신호를 읽을 수 있는 상태인지 (상태코드, 설명). 근거 없는 결론을 막기 위한 점검용.

        not_in_vcd : VCD에 이름이 없음 (unpacked array 등은 xsim이 VCD에 기록하지 않음)
        not_loaded : signals 필터로 적재하지 않음
        no_changes : 선언만 있고 값 변화 기록이 없음
        always_x   : 기록된 값이 전부 x/z (구동되지 않았거나 alias 표시 문제일 수 있음)
        ok         : 읽을 수 있음
        """
        if name not in self._signals:
            return ("not_in_vcd", "VCD에 없는 신호입니다. unpacked array(메모리)는 VCD에 기록되지 않으므로 "
                                  "포인터/출력 신호로 추론해야 합니다.")
        sig = self._signals[name]
        if self._keep is not None and sig.id not in self._keep:
            return ("not_loaded", "signals 필터에 없어 적재되지 않았습니다.")
        vals = self._values.get(sig.id, [])
        if not vals:
            return ("no_changes", "값 변화 기록이 없습니다 (until_ps 이전에 변화가 없었을 수 있음).")
        if all(set(v) <= {"x", "z"} for v in vals):
            return ("always_x", "기록된 값이 전부 x/z입니다. alias(net_group)와 교차 확인하세요.")
        return ("ok", "")

    def edges(self, clock: str, edge: str = "rising") -> list[int]:
        """클럭 에지 시각(ps) 목록. rising: 0->1/x/z 또는 x/z->1, falling: 1->0/x/z 또는 x/z->0."""
        if edge not in ("rising", "falling"):
            raise ValueError("edge는 'rising' 또는 'falling'")
        hi, lo = ("1", "0") if edge == "rising" else ("0", "1")
        out: list[int] = []
        prev = None
        for t, v in self.changes(clock):
            if prev is not None and (
                (prev == lo and v in (hi, "x", "z")) or (prev in ("x", "z") and v == hi)
            ):
                out.append(t)
            prev = v
        return out

    def sample_on_edge(self, clock: str, signals: list[str], t0_ps: int = 0,
                       t1_ps: int | None = None, edge: str = "rising",
                       when: str = "before") -> list[tuple[int, dict[str, str | None]]]:
        """클럭 에지마다 신호값을 샘플링한다: [(에지 시각, {신호: 값}), ...].

        when="before": 에지 직전 값 (플립플롭이 실제로 읽는 값, 기본).
        when="after" : 에지 직후 값 (에지에서 갱신된 결과).
        에지와 같은 시각에 바뀌는 신호는 'before'에서는 이전 값으로 보인다.
        """
        if when not in ("before", "after"):
            raise ValueError("when은 'before' 또는 'after'")
        out = []
        for t in self.edges(clock, edge):
            if t < t0_ps or (t1_ps is not None and t > t1_ps):
                continue
            at = t - 1 if when == "before" else t
            out.append((t, {n: self.value_at(n, at) for n in signals}))
        return out

    @staticmethod
    def to_int(value: str | None) -> int | None:
        """이진 문자열을 정수로. x/z가 있거나 None이면 None."""
        if not value or any(c not in "01" for c in value):
            return None
        return int(value, 2)

    # ---------- 파싱 ----------
    def _parse(self, lines) -> None:
        """줄 단위로 스트리밍 파싱한다 (수십~수백 MB VCD도 전체를 메모리에 올리지 않음)."""
        scope: list[str] = []
        header: list[str] = []
        in_header = True
        widths: dict[str, int] = {}
        now = 0
        for line in lines:
            if not line.endswith("\n"):      # 잘린 마지막 줄 버림
                break
            if in_header:
                header.extend(line.split())
                if "$enddefinitions" in header:
                    self._parse_header(header, scope)
                    widths = {sg.id: sg.width for sg in self._signals.values()}
                    if self._signal_filter is not None:
                        self._keep = {self.info(n).id for n in self._signal_filter}
                    in_header = False
                continue
            toks = line.split()
            k = 0
            while k < len(toks):
                t = toks[k]
                k += 1
                if t in _IGNORED:
                    continue
                c = t[0]
                if c == "#":
                    now = int(t[1:]) * self.timescale_ps
                    if self._until_ps is not None and now > self._until_ps:
                        return
                    self.end_time_ps = max(self.end_time_ps, now)
                elif c in "01xXzZ":
                    self._add(t[1:], now, t[0].lower())
                elif c in "bB" and k < len(toks):
                    vid = toks[k]
                    k += 1
                    self._add(vid, now, self._pad(t[1:].lower(), widths.get(vid, 1)))
                elif c in "rR" and k < len(toks):
                    vid = toks[k]
                    k += 1
                    self._add(vid, now, t[1:])

    def _parse_header(self, toks: list[str], scope: list[str]) -> None:
        i = 0
        while toks[i] != "$enddefinitions":
            t = toks[i]
            if t == "$timescale":
                j = toks.index("$end", i)
                self.timescale_ps = self._timescale("".join(toks[i + 1:j]))
                i = j
            elif t == "$scope":
                scope.append(toks[i + 2])
                i += 3
            elif t == "$upscope":
                if scope:
                    scope.pop()
            elif t == "$var":
                kind, width, vid, ref = toks[i + 1], int(toks[i + 2]), toks[i + 3], toks[i + 4]
                full = ".".join(scope + [ref])
                self._signals[full] = VcdSignal(full, vid, width, kind)
                self._id_names.setdefault(vid, []).append(full)
                i += 4
            i += 1

    def _add(self, vid: str, t: int, val: str) -> None:
        if vid not in self._id_names:     # 알 수 없는 ID (잘림 등)는 무시
            return
        if self._keep is not None and vid not in self._keep:
            return
        self._times.setdefault(vid, []).append(t)
        self._values.setdefault(vid, []).append(val)

    @staticmethod
    def _pad(bits: str, width: int) -> str:
        """VCD는 벡터의 앞쪽을 생략할 수 있다: 0/1이면 0으로, x/z면 그 문자로 확장."""
        if not bits or len(bits) >= width:
            return bits
        fill = "0" if bits[0] == "1" else bits[0]
        return fill * (width - len(bits)) + bits

    @staticmethod
    def _timescale(s: str) -> int:
        m = re.fullmatch(r"(\d+)(s|ms|us|ns|ps)", s)
        if not m:
            raise ValueError(f"지원하지 않는 $timescale: {s!r}")
        return int(m.group(1)) * _UNIT_PS[m.group(2)]