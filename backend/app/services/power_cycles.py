"""FrigoCore — An aggregate's day from its power draw.

The compressor either draws power or it doesn't: an aggregate's power
trace has two clear levels — a few tens of watts of controller standby
while it rests, hundreds or thousands of watts while it runs. The day is
cut into run and rest periods at a threshold learnt from the day itself,
with hysteresis and a short debounce, and summed up for the daily report:
time running and resting, starts, average lengths, duty share, energy and
the average power while running. A current trace works the same way
(no energy then — that needs the voltage).

Pure functions only, so the rules are unit-tested with synthetic traces.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

Point = tuple[datetime, float]

# A longer silence breaks the trace; nothing is assumed inside it.
MAX_GAP = timedelta(minutes=2)
# Below the threshold by this factor to count as stopped (hysteresis).
OFF_FACTOR = 0.7
# A change of state needs this many readings in a row (~20 s at 10 s a reading).
CONFIRM = 2
# The start-up surge is looked for in the first seconds of a run.
START_WINDOW = timedelta(seconds=30)
# Fewer readings than this make no report worth having.
MIN_READINGS = 30


@dataclass(frozen=True)
class PowerRun:
    running: bool
    start: datetime
    end: datetime
    # Cut by the day's edge or a gap in the data — not counted in averages.
    complete: bool

    @property
    def seconds(self) -> int:
        return int((self.end - self.start).total_seconds())


@dataclass(frozen=True)
class PowerDay:
    runs: list[PowerRun] = field(default_factory=list)
    threshold: float | None = None
    covered_seconds: int = 0
    energy_kwh: float | None = None
    avg_running_power: float | None = None
    avg_start_peak: float | None = None
    max_value: float | None = None

    @property
    def running_seconds(self) -> int:
        return sum(r.seconds for r in self.runs if r.running)

    @property
    def idle_seconds(self) -> int:
        return sum(r.seconds for r in self.runs if not r.running)

    @property
    def starts(self) -> int:
        """Times the compressor started during the day (a run under way at
        midnight or after a gap is not a start)."""
        return sum(
            1 for a, b in zip(self.runs, self.runs[1:])
            if b.running and not a.running and a.end == b.start
        )

    def _complete(self, running: bool) -> list[PowerRun]:
        return [r for r in self.runs if r.running == running and r.complete]

    @property
    def avg_run_seconds(self) -> int | None:
        runs = self._complete(True)
        return int(statistics.fmean(r.seconds for r in runs)) if runs else None

    @property
    def max_run_seconds(self) -> int | None:
        runs = self._complete(True)
        return max(r.seconds for r in runs) if runs else None

    @property
    def avg_idle_seconds(self) -> int | None:
        runs = self._complete(False)
        return int(statistics.fmean(r.seconds for r in runs)) if runs else None

    @property
    def duty_percent(self) -> float | None:
        total = self.running_seconds + self.idle_seconds
        return round(100 * self.running_seconds / total, 1) if total else None


def otsu_threshold(values: list[float]) -> float:
    """The cut between two levels that best separates them (Otsu's method on
    a 100-bin histogram)."""
    lo, hi = min(values), max(values)
    if hi <= lo:
        return hi
    bins = 100
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        counts[min(int((v - lo) / width), bins - 1)] += 1
    total = len(values)
    sum_all = sum((lo + (i + 0.5) * width) * c for i, c in enumerate(counts))
    best, best_cut = -1.0, lo + width
    w0 = 0
    sum0 = 0.0
    for i in range(bins - 1):
        w0 += counts[i]
        sum0 += (lo + (i + 0.5) * width) * counts[i]
        w1 = total - w0
        if w0 == 0 or w1 == 0:
            continue
        m0, m1 = sum0 / w0, (sum_all - sum0) / w1
        between = w0 * w1 * (m0 - m1) ** 2
        if between > best:
            best, best_cut = between, lo + (i + 1) * width
    return best_cut


def learn_threshold(values: list[float]) -> float:
    """Running vs resting. Two clear levels give Otsu's cut, taken on a log
    scale — the running level spreads over hundreds of watts (a compressor
    winds down from 1000 W to 450 W before it stops) while standby sits at a
    few tens, and a linear cut lands inside the running spread. A day with
    no clear resting level (running all day, or never) falls back to 30 %
    of the high readings, so the larger level counts as running."""
    cut = 10 ** otsu_threshold([math.log10(max(v, 0.0) + 10) for v in values]) - 10
    low = [v for v in values if v < cut]
    high = [v for v in values if v >= cut]
    if low and high:
        low_mean, high_mean = statistics.fmean(low), statistics.fmean(high)
        if high_mean >= 2 * low_mean + 30:
            # Otsu only says which reading is which level; the threshold
            # itself goes halfway between them on the log scale, clear of
            # both a steady standby and the run's wind-down.
            return math.sqrt(max(low_mean, 1.0) * high_mean)
    top = sorted(values)[int(0.95 * (len(values) - 1))]
    return 0.3 * top


def _pieces(points: list[Point]) -> list[list[Point]]:
    """Unbroken stretches of readings (a gap over MAX_GAP splits them)."""
    pieces: list[list[Point]] = []
    for p in points:
        if pieces and p[0] - pieces[-1][-1][0] <= MAX_GAP:
            pieces[-1].append(p)
        else:
            pieces.append([p])
    return pieces


def analyze_power(points: list[Point], start: datetime, end: datetime, energy: bool = True) -> PowerDay:
    """The run / rest periods of the day [start, end) from oldest-first power
    (or current) readings. With `energy` the readings are watts and the day's
    kWh is integrated from them."""
    day = [p for p in points if start <= p[0] < end]
    if len(day) < MIN_READINGS:
        return PowerDay()
    threshold = learn_threshold([v for _, v in day])
    off_below = threshold * OFF_FACTOR

    runs: list[PowerRun] = []
    covered = 0.0
    kwh = 0.0
    running_values: list[float] = []
    start_peaks: list[float] = []
    for piece in _pieces(day):
        covered += (piece[-1][0] - piece[0][0]).total_seconds()
        for (t0, v0), (t1, v1) in zip(piece, piece[1:]):
            kwh += (v0 + v1) / 2 * (t1 - t0).total_seconds() / 3_600_000
        state = piece[0][1] > threshold
        since = piece[0][0]
        streak: list[Point] = []
        first_run = True
        for t, v in piece:
            if state:
                running_values.append(v)
            flips = v < off_below if state else v > threshold
            streak = streak + [(t, v)] if flips else []
            if len(streak) >= CONFIRM:
                changed_at = streak[0][0]
                if changed_at > since:
                    runs.append(PowerRun(state, since, changed_at, complete=not first_run))
                first_run = False
                state, since, streak = not state, changed_at, []
        runs.append(PowerRun(state, since, piece[-1][0], complete=False))

    for r in runs:
        if r.running and r.complete:
            surge = [v for t, v in day if r.start <= t < r.start + START_WINDOW]
            if surge:
                start_peaks.append(max(surge))

    return PowerDay(
        runs=runs,
        threshold=round(threshold, 1),
        covered_seconds=int(covered),
        energy_kwh=round(kwh, 2) if energy else None,
        avg_running_power=round(statistics.fmean(running_values), 1) if running_values else None,
        avg_start_peak=round(statistics.fmean(start_peaks), 1) if start_peaks else None,
        max_value=round(max(v for _, v in day), 1),
    )
