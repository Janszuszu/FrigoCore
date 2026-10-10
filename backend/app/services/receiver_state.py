"""FrigoCore — Receiver working state inferred from temperatures.

A receiver (cold room, freezer, display case) is in one of three states
the owner cares about, and none of them is reported by the sensors
directly — they're read off the trends of the chamber and evaporator
traces over the last few minutes:

- COOLING: the evaporator is colder than the chamber air and either the
  chamber is falling or the evaporator is plunging (the compressor has
  just started and the air hasn't followed yet). How much colder varies a
  lot by installation — about 1.5 °C on the Biskupiec freezer, 10 °C on its
  cold room — so only a small gap is required; the trends decide.
- DEFROST: the evaporator is warmer than the chamber air (or above 0 °C in
  a freezer) — only a defrost heater or hot gas does that. Or the chamber
  is well above the cut-in and not being cooled: the controller would be
  running the compressor unless it were defrosting.
- IDLE: neither — the compressor is off and the evaporator is drifting
  back towards the chamber temperature.

Without an evaporator sensor only the chamber trend and the cut-in are
used. Too little recent data gives UNKNOWN.

Pure functions only — the API feeds them readings, so the rules can be
unit-tested with synthetic traces.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta

COOLING = "cooling"
IDLE = "idle"
DEFROST = "defrost"
UNKNOWN = "unknown"

Point = tuple[datetime, float]

# Each decision looks at this much of the most recent history — short, so
# a defrost that just ended doesn't still dominate the trend.
WINDOW = timedelta(minutes=6)
# ...and needs at least this many readings spread over this long, so a
# single reading after an outage doesn't produce a confident answer.
MIN_POINTS = 2
MIN_SPAN = timedelta(seconds=90)

# Evaporator warmer than the chamber by this much while warming fast, or
# by the larger margin outright, means it is being heated. (A sensor on a
# resting coil can read ~1 °C above the air, so warm alone isn't enough.)
DEFROST_MARGIN = 1.0
DEFROST_EVAPORATOR_RISE = 0.3
DEFROST_CLEAR_MARGIN = 5.0
# Chamber air climbing this fast (°C/min) without cooling is a defrost —
# idle drift is a few tenths of a degree per minute at most.
DEFROST_CHAMBER_RISE = 0.5
# Chamber this far above the cut-in without being cooled means defrost.
DEFROST_ABOVE_CUT_IN = 2.0
# Cooling needs the evaporator at least this much colder than the chamber...
COOLING_MIN_GAP = 0.5
# ...and the chamber falling at least this fast (°C/min)...
COOLING_CHAMBER_RATE = -0.05
# ...or the evaporator falling at least this fast (°C/min)...
COOLING_EVAPORATOR_RATE = -0.3
# ...and the evaporator not warming faster than this — once it climbs, the
# compressor has stopped even if the chamber trend still lags behind.
COOLING_MAX_EVAPORATOR_RISE = 0.3

# The state is replayed minute by minute over this much history to find
# when it began and to time the cooling / idle phases of the cycle.
TIMELINE_LOOKBACK = timedelta(hours=6)
TIMELINE_STEP = timedelta(minutes=1)
# A phase shorter than this is a wobble at a transition, not a real phase.
MIN_PHASE = timedelta(minutes=2)

# Estimates beyond a day mean the room is barely cooling; don't show one.
MAX_MINUTES_TO_TARGET = 24 * 60


@dataclass(frozen=True)
class ReceiverAnalysis:
    state: str
    # When the current state began; None if unknown or before the lookback.
    state_since: datetime | None = None
    # While cooling towards a target (the cut-out): estimated minutes until reaching it.
    minutes_to_target: float | None = None
    # Chamber temperature trend over the window, °C per minute.
    chamber_rate: float | None = None
    # The refrigeration cycle as two stopwatches: the phase now running
    # ("cooling" or "idle" — defrost counts as idle, nothing is cooling),
    # and each phase's duration — the running one so far, the other its
    # last complete run. None where the history doesn't cover it.
    cycle_phase: str | None = None
    cooling_seconds: int | None = None
    idle_seconds: int | None = None


class _Trace:
    """Sorted readings with their timestamps, so a window is a bisect."""

    __slots__ = ("points", "times")

    def __init__(self, points: list[Point]):
        self.points = points
        self.times = [p[0] for p in points]

    def window(self, at: datetime) -> list[Point]:
        """Readings in (at - WINDOW, at]."""
        lo = bisect.bisect_right(self.times, at - WINDOW)
        hi = bisect.bisect_right(self.times, at)
        return self.points[lo:hi]


def _usable(points: list[Point]) -> bool:
    return len(points) >= MIN_POINTS and points[-1][0] - points[0][0] >= MIN_SPAN


def slope_per_minute(points: list[Point]) -> float:
    """Least-squares trend of `points`, °C per minute."""
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 60 for t, _ in points]
    ys = [v for _, v in points]
    n = len(points)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def classify(
    chamber: list[Point],
    evaporator: list[Point] | None,
    at: datetime,
    cut_in: float | None = None,
) -> str:
    """The receiver's state at `at`, from readings up to that moment."""
    return _classify(_Trace(chamber), _Trace(evaporator) if evaporator else None, at, cut_in)


def _classify(chamber: _Trace, evaporator: _Trace | None, at: datetime, cut_in: float | None) -> str:
    c_pts = chamber.window(at)
    if not _usable(c_pts):
        return UNKNOWN
    c = c_pts[-1][1]
    c_rate = slope_per_minute(c_pts)
    chamber_falling = c_rate <= COOLING_CHAMBER_RATE

    e_pts = evaporator.window(at) if evaporator else []
    if _usable(e_pts):
        e = e_pts[-1][1]
        e_rate = slope_per_minute(e_pts)
        heated = e > c + DEFROST_CLEAR_MARGIN or (e > c + DEFROST_MARGIN and e_rate >= DEFROST_EVAPORATOR_RISE)
        if heated or (c < -2 and e > 0):
            return DEFROST
        if (
            e <= c - COOLING_MIN_GAP
            and e_rate <= COOLING_MAX_EVAPORATOR_RISE
            and (chamber_falling or e_rate <= COOLING_EVAPORATOR_RATE)
        ):
            return COOLING
    elif chamber_falling:
        # No (recent) evaporator data — the chamber trend is all there is.
        return COOLING

    if c_rate >= DEFROST_CHAMBER_RISE or (cut_in is not None and c > cut_in + DEFROST_ABOVE_CUT_IN):
        return DEFROST
    return IDLE


Segment = tuple[str, datetime, datetime]  # value, start, end


def _segments(samples: list[tuple[datetime, str]], end: datetime) -> list[Segment]:
    """Runs of equal values; each run lasts until the next one starts."""
    runs: list[list] = []
    for t, value in samples:
        if runs and runs[-1][0] == value:
            continue
        if runs:
            runs[-1][2] = t
        runs.append([value, t, end])
    return [tuple(r) for r in runs]


def _merge_short(segments: list[Segment]) -> list[Segment]:
    """Fold phases shorter than MIN_PHASE into the one before them (the
    current, still-running phase is kept however short)."""
    merged: list[list] = []
    for i, (value, start, end) in enumerate(segments):
        is_last = i == len(segments) - 1
        if merged and (value == merged[-1][0] or (not is_last and end - start < MIN_PHASE)):
            merged[-1][2] = end
        else:
            merged.append([value, start, end])
    return [tuple(m) for m in merged]


def _snap_to_turns(phases: list[Segment], chamber: _Trace) -> list[Segment]:
    """Move each phase change back to the moment the controller switched.

    The readings come straight from the controller's own probe, so the
    switch is exactly where the chamber turns: cooling starts at its peak
    and stops at its trough. Detection trails that by a minute or two
    (a trend needs a few readings), so look back one window from where the
    change was noticed for the latest peak or trough."""
    snapped = [list(ph) for ph in phases]
    for i in range(1, len(snapped)):
        value, start, _ = snapped[i]
        candidates = chamber.window(start)
        if not candidates:
            continue
        pick = max if value == "cooling" else min
        turn = pick(candidates, key=lambda p: (p[1], p[0]) if value == "cooling" else (p[1], -p[0].timestamp()))[0]
        if snapped[i - 1][1] < turn <= start:
            snapped[i][1] = turn
            snapped[i - 1][2] = turn
    return [tuple(ph) for ph in snapped]


def _cycle(phases: list[Segment], now: datetime) -> tuple[str | None, int | None, int | None]:
    """(running phase, cooling seconds, idle seconds). A phase that began
    before the lookback has an unknown length, so only phases with a phase
    before them are timed."""
    if not phases:
        return None, None, None
    current, start, _ = phases[-1]
    running = int((now - start).total_seconds()) if len(phases) > 1 else None
    previous = None
    if len(phases) > 2:
        _, p_start, p_end = phases[-2]
        previous = int((p_end - p_start).total_seconds())
    if current == "cooling":
        return current, running, previous
    return current, previous, running


def analyze(
    chamber: list[Point],
    evaporator: list[Point] | None,
    now: datetime,
    target: float | None = None,
    cut_in: float | None = None,
) -> ReceiverAnalysis:
    """State, how long it has lasted, the cycle stopwatches and, while
    cooling, time to `target`.

    `chamber` and `evaporator` must be sorted oldest-first and should cover
    TIMELINE_LOOKBACK + WINDOW for the history-based values.
    """
    c_trace = _Trace(chamber)
    e_trace = _Trace(evaporator) if evaporator else None
    state = _classify(c_trace, e_trace, now, cut_in)
    if state == UNKNOWN:
        return ReceiverAnalysis(state=UNKNOWN)

    # Replay the state minute by minute; a gap in the data (UNKNOWN) keeps
    # the previous state rather than splitting a phase in two.
    samples: list[tuple[datetime, str]] = []
    t = now - TIMELINE_LOOKBACK
    while t < now:
        s = _classify(c_trace, e_trace, t, cut_in)
        if s == UNKNOWN:
            s = samples[-1][1] if samples else None
        if s is not None:
            samples.append((t, s))
        t += TIMELINE_STEP
    samples.append((now, state))

    states = _segments(samples, now)
    since = states[-1][1] if len(states) > 1 else None
    phases = _merge_short(_segments([(t, "cooling" if s == COOLING else "idle") for t, s in samples], now))
    phases = _snap_to_turns(phases, c_trace)
    cycle_phase, cooling_seconds, idle_seconds = _cycle(phases, now)

    c_pts = c_trace.window(now)
    rate = slope_per_minute(c_pts)
    current = c_pts[-1][1]
    minutes = None
    if state == COOLING and target is not None and current > target and rate < -0.01:
        estimate = (current - target) / -rate
        if estimate <= MAX_MINUTES_TO_TARGET:
            minutes = round(estimate, 1)

    return ReceiverAnalysis(
        state=state,
        state_since=since,
        minutes_to_target=minutes,
        chamber_rate=round(rate, 3),
        cycle_phase=cycle_phase,
        cooling_seconds=cooling_seconds,
        idle_seconds=idle_seconds,
    )
