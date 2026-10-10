"""FrigoCore — Receiver working state inferred from temperatures.

A receiver (cold room, freezer, display case) is in one of three states
the owner cares about, and none of them is reported by the sensors
directly — they're read off the shape of the chamber and evaporator traces
over the last few minutes:

- COOLING: the evaporator sits well below the chamber air and isn't
  warming up — refrigerant is flowing and pulling heat out.
- DEFROST: the evaporator is warmer than the chamber air (or above 0 °C in
  a freezer) — only a defrost heater or hot gas does that.
- IDLE: neither — the compressor is off and the evaporator is drifting
  back towards the chamber temperature.

Without an evaporator sensor defrost can't be told apart from an idle
period, so only the chamber trend is used: falling means cooling,
anything else idle. Too little recent data gives UNKNOWN.

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

# Each decision looks at this much of the most recent history.
WINDOW = timedelta(minutes=15)
# ...and needs at least this many readings spread over this long, so a
# single reading after an outage doesn't produce a confident answer.
MIN_POINTS = 3
MIN_SPAN = timedelta(minutes=4)

# Evaporator this much warmer than the chamber means it is being heated.
DEFROST_MARGIN = 1.0
# Evaporator at least this much colder than the chamber means it is cooling...
COOLING_GAP = 3.0
# ...unless it is warming faster than this (°C/min) — the compressor has
# just stopped and the coil is drifting back up.
COOLING_MAX_EVAPORATOR_RISE = 0.2
# Chamber-only fallback: falling at least this fast (°C/min) is cooling.
CHAMBER_ONLY_COOLING_RATE = -0.05

# How far back to look for the moment the current state began.
SINCE_LOOKBACK = timedelta(hours=3)
SINCE_STEP = timedelta(minutes=2)

# Estimates beyond a day mean the room is barely cooling; don't show one.
MAX_MINUTES_TO_SETPOINT = 24 * 60


@dataclass(frozen=True)
class ReceiverAnalysis:
    state: str
    # When the current state began; None if unknown or longer ago than
    # SINCE_LOOKBACK.
    state_since: datetime | None = None
    # While cooling towards a setpoint: estimated minutes until reaching it.
    minutes_to_setpoint: float | None = None
    # Chamber temperature trend over the window, °C per minute.
    chamber_rate: float | None = None


def _window(points: list[Point], at: datetime) -> list[Point]:
    """Readings in (at - WINDOW, at]; `points` must be sorted by time."""
    times = [p[0] for p in points]
    lo = bisect.bisect_right(times, at - WINDOW)
    hi = bisect.bisect_right(times, at)
    return points[lo:hi]


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


def classify(chamber: list[Point], evaporator: list[Point] | None, at: datetime) -> str:
    """The receiver's state at `at`, from readings up to that moment."""
    c_pts = _window(chamber, at)
    if not _usable(c_pts):
        return UNKNOWN
    c = c_pts[-1][1]

    e_pts = _window(evaporator, at) if evaporator else []
    if _usable(e_pts):
        e = e_pts[-1][1]
        if e > c + DEFROST_MARGIN or (c < -2 and e > 0):
            return DEFROST
        if e < c - COOLING_GAP and slope_per_minute(e_pts) <= COOLING_MAX_EVAPORATOR_RISE:
            return COOLING
        return IDLE

    # No (recent) evaporator data — the chamber trend is all there is.
    return COOLING if slope_per_minute(c_pts) <= CHAMBER_ONLY_COOLING_RATE else IDLE


def analyze(
    chamber: list[Point],
    evaporator: list[Point] | None,
    now: datetime,
    setpoint: float | None = None,
) -> ReceiverAnalysis:
    """State, how long it has lasted and, while cooling, time to setpoint.

    `chamber` and `evaporator` must be sorted oldest-first and should
    cover at least SINCE_LOOKBACK + WINDOW for `state_since` to be found.
    """
    state = classify(chamber, evaporator, now)
    if state == UNKNOWN:
        return ReceiverAnalysis(state=UNKNOWN)

    # Step back until the state differs; the last matching step is when
    # the current state began (to within SINCE_STEP).
    since = None
    t = now - SINCE_STEP
    while t >= now - SINCE_LOOKBACK:
        if classify(chamber, evaporator, t) != state:
            since = t + SINCE_STEP
            break
        t -= SINCE_STEP

    c_pts = _window(chamber, now)
    rate = slope_per_minute(c_pts)
    current = c_pts[-1][1]
    minutes = None
    if state == COOLING and setpoint is not None and current > setpoint and rate < -0.01:
        estimate = (current - setpoint) / -rate
        if estimate <= MAX_MINUTES_TO_SETPOINT:
            minutes = round(estimate, 1)

    return ReceiverAnalysis(
        state=state,
        state_since=since,
        minutes_to_setpoint=minutes,
        chamber_rate=round(rate, 3),
    )
