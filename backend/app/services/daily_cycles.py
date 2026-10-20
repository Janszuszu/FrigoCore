"""FrigoCore — Daily analysis of a receiver's refrigeration cycles.

Run once a day, just after midnight, over the day that has ended: the
chamber trace is cut into cooling runs (temperature falling from a peak to
the trough where the compressor stops) and idle runs (rising from that
trough to the next peak, where it starts again), and the defrosts are
picked out with their start, length and peak temperature. The result
feeds the daily report.

The steps:

1. Readings are averaged per minute and lightly median-smoothed, so a
   single bad reading or 0.1 °C quantisation noise can't make a cycle.
   A gap longer than MAX_GAP splits the day — nothing is guessed inside it.
2. Turning points are found with hysteresis: a peak (or trough) only counts
   once the temperature has come back from it by at least `delta`. delta
   is learnt from the day itself — a fraction of the receiver's typical
   swing — so it suits a display case cycling over 1 °C and a cold room
   cycling over 5 °C alike.
3. Falling runs are cooling, rising runs idle — unless they are defrost.
   A defrost is a rise during which, for at least MIN_DEFROST, either the
   evaporator is heated (warmer than the air the way only a heater or hot
   gas makes it) or the air is far above its ordinary peaks with the
   evaporator not cooling it (an off-cycle defrost). An open door warms
   the air while the coil stays cold, so it is no defrost. Without an
   evaporator sensor the chamber-only state rules decide, or a rise whose
   peak towers over the day's ordinary idle peaks.
4. A defrost lasts from the trough it starts at to its peak (the heating);
   the pull-down after it — from the peak back to the day's ordinary peak
   level — is reported separately as the recovery.

Pure functions only, so the rules are unit-tested with synthetic traces.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.services.receiver_state import (
    DEFROST,
    DEFROST_CLEAR_MARGIN,
    DEFROST_EVAPORATOR_RISE,
    DEFROST_MARGIN,
    Point,
    _classify,
    _Trace,
    _usable,
    slope_per_minute,
)

STEP = timedelta(minutes=1)
# Longer than this without a reading splits the day; no cycle spans it.
MAX_GAP = timedelta(minutes=10)
# Median filter width, in minutes.
SMOOTH = 5
# Hysteresis: never finer than this (°C) ...
MIN_DELTA = 0.2
# ... and otherwise this fraction of the day's median swing.
DELTA_FRACTION = 0.3
# A rise counts as a defrost when the state rules call it one for this long...
MIN_DEFROST = timedelta(minutes=4)
# ... or when its peak is this far above the median idle peak (°C) ...
DEFROST_PEAK_MARGIN = 3.0
# ... and the swing is at least this many times the median swing.
DEFROST_SWING_FACTOR = 2.5
# An evaporator within this much of the air (°C) isn't cooling it — a
# running compressor keeps the coil some 10 °C below.
OFF_CYCLE_GAP = 4.0
# A "defrost" longer than this is the receiver switched off or failing,
# reported apart and kept out of the defrost count.
MAX_DEFROST = timedelta(hours=2)


@dataclass(frozen=True)
class Run:
    kind: str  # "cooling" | "idle" | "defrost" | "off" (a long warm-up: switched off or failing)
    start: datetime
    end: datetime
    start_temp: float
    end_temp: float

    @property
    def seconds(self) -> int:
        return int((self.end - self.start).total_seconds())


@dataclass(frozen=True)
class Defrost:
    start: datetime
    end: datetime  # the peak — heating over
    peak: float
    # From the peak until the chamber is back at the ordinary peak level;
    # None when the day ends (or data stops) before it gets there.
    recovery_seconds: int | None

    @property
    def seconds(self) -> int:
        return int((self.end - self.start).total_seconds())


@dataclass(frozen=True)
class DayAnalysis:
    runs: list[Run] = field(default_factory=list)
    defrosts: list[Defrost] = field(default_factory=list)
    # Minutes of the day with data behind them.
    covered_seconds: int = 0
    min_temp: float | None = None
    max_temp: float | None = None
    avg_temp: float | None = None
    delta: float | None = None

    def _complete(self, kind: str) -> list[Run]:
        return [r for r in self.runs if r.kind == kind]

    @property
    def cooling_runs(self) -> list[Run]:
        return self._complete("cooling")

    @property
    def idle_runs(self) -> list[Run]:
        return self._complete("idle")

    @property
    def cooling_seconds(self) -> int:
        return sum(r.seconds for r in self.cooling_runs)

    @property
    def idle_seconds(self) -> int:
        return sum(r.seconds for r in self.idle_runs)

    @property
    def duty_percent(self) -> float | None:
        total = self.cooling_seconds + self.idle_seconds
        return round(100 * self.cooling_seconds / total, 1) if total else None


def resample(points: list[Point], start: datetime, end: datetime) -> list[tuple[datetime, float] | None]:
    """Per-minute means over [start, end); a minute without readings carries
    the last value on for up to MAX_GAP, after that it is None (a gap)."""
    minutes = int((end - start) / STEP)
    sums = [0.0] * minutes
    counts = [0] * minutes
    for t, v in points:
        i = int((t - start) / STEP)
        if 0 <= i < minutes:
            sums[i] += v
            counts[i] += 1
    out: list[tuple[datetime, float] | None] = []
    last: float | None = None
    last_seen: datetime | None = None
    # A reading just before the day carries into its first minutes.
    before = [p for p in points if p[0] < start]
    if before:
        last_seen, last = before[-1]
    for i in range(minutes):
        t = start + i * STEP
        if counts[i]:
            last, last_seen = sums[i] / counts[i], t
            out.append((t, last))
        elif last is not None and last_seen is not None and t - last_seen <= MAX_GAP:
            out.append((t, last))
        else:
            out.append(None)
    return out


def _smooth(series: list[tuple[datetime, float] | None]) -> list[tuple[datetime, float] | None]:
    half = SMOOTH // 2
    out: list[tuple[datetime, float] | None] = []
    for i, s in enumerate(series):
        if s is None:
            out.append(None)
            continue
        window = [x[1] for x in series[max(0, i - half): i + half + 1] if x is not None]
        out.append((s[0], statistics.median(window)))
    return out


def _pieces(series: list[tuple[datetime, float] | None]) -> list[list[tuple[datetime, float]]]:
    """Unbroken stretches of the series (gaps split it)."""
    pieces: list[list[tuple[datetime, float]]] = [[]]
    for s in series:
        if s is None:
            if pieces[-1]:
                pieces.append([])
        else:
            pieces[-1].append(s)
    return [p for p in pieces if len(p) > 1]


def turning_points(piece: list[tuple[datetime, float]], delta: float) -> list[tuple[datetime, float, str]]:
    """Confirmed peaks and troughs, alternating: (time, temp, "peak"|"trough").
    The first and last points of the piece are not turns — the runs touching
    them are cut by the piece's edges and can't be timed."""
    turns: list[tuple[datetime, float, str]] = []
    # Until the first reversal both extremes are tracked; that first one is
    # only a real turn if the trace had moved towards it by delta before.
    direction: str | None = None  # "up": rising, watching for a peak; "down": the reverse
    hi = lo = piece[0]
    for t, v in piece[1:]:
        if direction != "down":
            if v > hi[1]:
                hi = (t, v)
            elif hi[1] - v >= delta:
                if direction == "up" or hi[1] - lo[1] >= delta and lo[0] < hi[0]:
                    turns.append((hi[0], hi[1], "peak"))
                direction, lo = "down", (t, v)
                continue
        if direction != "up":
            if v < lo[1]:
                lo = (t, v)
            elif v - lo[1] >= delta:
                if direction == "down" or hi[1] - lo[1] >= delta and hi[0] < lo[0]:
                    turns.append((lo[0], lo[1], "trough"))
                direction, hi = "up", (t, v)
    return turns


def _heated(chamber: list[Point], evaporator: list[Point]) -> bool:
    """The coil warmer than the air in a way only a heater or hot gas does —
    the same test the live state rules use for defrost."""
    if not chamber:
        return False
    c, e = chamber[-1][1], evaporator[-1][1]
    if e > c + DEFROST_CLEAR_MARGIN or (c < -2 and e > 0):
        return True
    return e > c + DEFROST_MARGIN and slope_per_minute(evaporator) >= DEFROST_EVAPORATOR_RISE


def _swings(turns: list[tuple[datetime, float, str]]) -> list[float]:
    return [abs(b[1] - a[1]) for a, b in zip(turns, turns[1:])]


def analyze_day(
    chamber: list[Point],
    evaporator: list[Point] | None,
    start: datetime,
    end: datetime,
    cut_in: float | None = None,
    cut_out: float | None = None,
) -> DayAnalysis:
    """The cycles of the day [start, end). `chamber` / `evaporator` are
    oldest-first readings; a few minutes before `start` help the first
    minutes along."""
    series = _smooth(resample(chamber, start, end))
    pieces = _pieces(series)
    if not pieces:
        return DayAnalysis()
    values = [v for p in pieces for _, v in p]

    # Learn the hysteresis from the day: first pass at the floor, then a
    # fraction of the median swing it found.
    delta = MIN_DELTA
    first = [s for p in pieces for s in _swings(turning_points(p, delta))]
    if first:
        delta = max(MIN_DELTA, DELTA_FRACTION * statistics.median(first))

    raw: list[Run] = []
    for p in pieces:
        turns = turning_points(p, delta)
        for a, b in zip(turns, turns[1:]):
            kind = "cooling" if a[2] == "peak" else "idle"
            raw.append(Run(kind, a[0], b[0], a[1], b[1]))

    swings = [abs(r.end_temp - r.start_temp) for r in raw]
    median_swing = statistics.median(swings) if swings else 0.0
    idle_peaks = [r.end_temp for r in raw if r.kind == "idle"]
    median_peak = statistics.median(idle_peaks) if idle_peaks else None
    # Air this far above the day's ordinary peaks is no idle drift.
    high = median_peak + DEFROST_PEAK_MARGIN if median_peak is not None else None

    # Minute by minute, which minutes look like a defrost:
    # - the evaporator is heated (warmer than the air the way only a heater
    #   or hot gas makes it), or
    # - the air is far above its ordinary peaks while the evaporator isn't
    #   cooling it (within OFF_CYCLE_GAP of the air) — an off-cycle defrost,
    #   the compressor simply held off. An open door warms the air too, but
    #   the compressor keeps the coil cold, so it doesn't count.
    # Without an evaporator sensor the chamber-only live state rules stand in.
    c_trace = _Trace(chamber)
    e_trace = _Trace(evaporator) if evaporator else None
    defrost_minutes: set[datetime] = set()
    for p in pieces:
        for t, c in p:
            at = t + STEP
            e_pts = e_trace.window(at) if e_trace is not None else []
            if _usable(e_pts):
                c_pts = c_trace.window(at)
                uncooled = e_pts[-1][1] >= c - OFF_CYCLE_GAP
                if _heated(c_pts, e_pts) or (high is not None and c >= high and uncooled):
                    defrost_minutes.add(t)
            elif _classify(c_trace, None, at, cut_in, cut_out) == DEFROST:
                defrost_minutes.add(t)

    def is_defrost(r: Run) -> bool:
        flagged = sum(1 for m in defrost_minutes if r.start <= m <= r.end)
        if flagged * STEP >= MIN_DEFROST:
            return True
        # With an evaporator its verdict is final; without one a rise that
        # towers over the ordinary idle peaks is taken for a defrost.
        return (
            e_trace is None
            and high is not None
            and r.end_temp >= high
            and r.end_temp - r.start_temp >= DEFROST_SWING_FACTOR * max(median_swing, MIN_DELTA)
        )

    runs = [Run("defrost", r.start, r.end, r.start_temp, r.end_temp) if r.kind == "idle" and is_defrost(r) else r for r in raw]

    # The ordinary peak level, from idle runs only, now that defrosts are out.
    ordinary = [r.end_temp for r in runs if r.kind == "idle"]
    back_at = statistics.median(ordinary) if ordinary else None

    # A defrost that wobbles (dips and climbs again before the pull-down)
    # comes out as defrost, cooling, defrost: one defrost while the dip
    # stays above the ordinary peak level.
    merged: list[Run] = []
    for r in runs:
        if (
            r.kind == "defrost"
            and len(merged) >= 2
            and merged[-2].kind == "defrost"
            and merged[-1].kind == "cooling"
            and merged[-1].end == r.start
            and back_at is not None
            and merged[-1].end_temp > back_at
        ):
            first = merged[-2]
            del merged[-2:]
            top = max((first, r), key=lambda x: x.end_temp)
            merged.append(Run("defrost", first.start, top.end, first.start_temp, top.end_temp))
            continue
        merged.append(r)
    runs = merged
    defrosts: list[Defrost] = []
    for i, r in enumerate(runs):
        if r.kind != "defrost":
            continue
        recovery = None
        after = None
        if back_at is not None:
            after = next((t for p in pieces for t, v in p if t > r.end and v <= back_at), None)
            if after is not None:
                recovery = int((after - r.end).total_seconds())
        # Warm from the start until back at the ordinary level: hours of that
        # is the receiver off or failing, not a defrost.
        if (after or pieces[-1][-1][0]) - r.start > MAX_DEFROST:
            runs[i] = Run("off", r.start, r.end, r.start_temp, r.end_temp)
            continue
        defrosts.append(Defrost(r.start, r.end, round(r.end_temp, 1), recovery))

    return DayAnalysis(
        runs=runs,
        defrosts=defrosts,
        covered_seconds=sum(len(p) for p in pieces) * int(STEP.total_seconds()),
        min_temp=round(min(values), 1),
        max_temp=round(max(values), 1),
        avg_temp=round(statistics.fmean(values), 1),
        delta=round(delta, 2),
    )
