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

# How far back to look for the moment the current state began.
SINCE_LOOKBACK = timedelta(hours=3)
SINCE_STEP = timedelta(minutes=2)

# Estimates beyond a day mean the room is barely cooling; don't show one.
MAX_MINUTES_TO_TARGET = 24 * 60


@dataclass(frozen=True)
class ReceiverAnalysis:
    state: str
    # When the current state began; None if unknown or longer ago than
    # SINCE_LOOKBACK.
    state_since: datetime | None = None
    # While cooling towards a target (the cut-out): estimated minutes until reaching it.
    minutes_to_target: float | None = None
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


def classify(
    chamber: list[Point],
    evaporator: list[Point] | None,
    at: datetime,
    cut_in: float | None = None,
) -> str:
    """The receiver's state at `at`, from readings up to that moment."""
    c_pts = _window(chamber, at)
    if not _usable(c_pts):
        return UNKNOWN
    c = c_pts[-1][1]
    c_rate = slope_per_minute(c_pts)
    chamber_falling = c_rate <= COOLING_CHAMBER_RATE

    e_pts = _window(evaporator, at) if evaporator else []
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


def analyze(
    chamber: list[Point],
    evaporator: list[Point] | None,
    now: datetime,
    target: float | None = None,
    cut_in: float | None = None,
) -> ReceiverAnalysis:
    """State, how long it has lasted and, while cooling, time to `target`.

    `chamber` and `evaporator` must be sorted oldest-first and should
    cover at least SINCE_LOOKBACK + WINDOW for `state_since` to be found.
    """
    state = classify(chamber, evaporator, now, cut_in)
    if state == UNKNOWN:
        return ReceiverAnalysis(state=UNKNOWN)

    # Step back until the state differs; the last matching step is when
    # the current state began (to within SINCE_STEP).
    since = None
    t = now - SINCE_STEP
    while t >= now - SINCE_LOOKBACK:
        if classify(chamber, evaporator, t, cut_in) != state:
            since = t + SINCE_STEP
            break
        t -= SINCE_STEP

    c_pts = _window(chamber, now)
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
    )
