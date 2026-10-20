"""Daily receiver analysis (cooling / idle / defrost) and the Raport API."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.enums import UserRole
from app.models.receiver import Receiver
from app.services.daily_cycles import analyze_day
from app.services.daily_reports import day_bounds, run_pending, seconds_until_next_run
from tests.conftest import auth_headers
from tests.helpers import make_object
from tests.test_receivers import _assign, _readings, _sensor

START = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)  # 20.10 00:00 in Warsaw
END = START + timedelta(days=1)

COOL_MIN, IDLE_MIN = 6, 10  # minutes per phase
LOW, HIGH = 3.0, 5.0


def synthetic_day(
    defrosts: tuple[int, ...] = (),
    doors: tuple[int, ...] = (),
    off: tuple[int, int] | None = None,
    gap: tuple[int, int] | None = None,
    defrost_minutes: int = 30,
    defrost_peak: float = 12.0,
):
    """Two readings a minute over the day: a saw-tooth cycling LOW..HIGH
    (falling COOL_MIN minutes, rising IDLE_MIN), the evaporator cold while
    cooling and near the air while idle. A defrost (at the given minutes of
    the day) warms the air to `defrost_peak` with the evaporator heated far
    above it, then a pull-down; a door opening warms the air while the
    evaporator stays cold; `off` holds the air rising for hours; `gap`
    leaves minutes without readings."""
    chamber, evaporator = [], []
    special: dict[int, tuple[float, float]] = {}
    for d in defrosts:
        for i in range(defrost_minutes):
            c = LOW + (defrost_peak - LOW) * (i + 1) / defrost_minutes
            special[d + i] = (c, c + 15)
        for i in range(10):  # pull-down
            c = defrost_peak - (defrost_peak - LOW) * (i + 1) / 10
            special[d + defrost_minutes + i] = (c, -8.0)
    for d in doors:
        for i in range(5):
            special[d + i] = (LOW + 1.5 * (i + 1), -8.0)
        for i in range(5):
            special[d + 5 + i] = (LOW + 7.5 - 1.5 * (i + 1), -8.0)
    if off:
        a, b = off
        for i in range(a, b):
            c = LOW + 15 * min(1.0, (i - a) / 60)
            special[i] = (c, c - 0.5)
    period = COOL_MIN + IDLE_MIN
    for m in range(24 * 60):
        if gap and gap[0] <= m < gap[1]:
            continue
        if m in special:
            c, e = special[m]
        else:
            k = m % period
            if k < IDLE_MIN:
                c, e = LOW + (HIGH - LOW) * k / IDLE_MIN, LOW - 1.0
            else:
                c, e = HIGH - (HIGH - LOW) * (k - IDLE_MIN) / COOL_MIN, -8.0
        for s in (0, 30):
            t = START + timedelta(minutes=m, seconds=s)
            chamber.append((t, round(c, 1)))
            evaporator.append((t, round(e, 1)))
    return chamber, evaporator


def test_cycles_are_counted_and_timed():
    chamber, evaporator = synthetic_day()
    a = analyze_day(chamber, evaporator, START, END, cut_in=HIGH, cut_out=LOW)
    # 90 cycles a day; the edge runs are cut and not counted.
    assert len(a.cooling_runs) == pytest.approx(90, abs=1)
    assert len(a.idle_runs) == pytest.approx(90, abs=1)
    assert a.duty_percent == pytest.approx(100 * COOL_MIN / (COOL_MIN + IDLE_MIN), abs=3)
    assert a.defrosts == []
    assert a.min_temp == pytest.approx(LOW, abs=0.3) and a.max_temp == pytest.approx(HIGH, abs=0.3)


def test_defrosts_found_with_start_length_and_recovery():
    chamber, evaporator = synthetic_day(defrosts=(6 * 60 + 2, 14 * 60 + 2))
    a = analyze_day(chamber, evaporator, START, END, cut_in=HIGH, cut_out=LOW)
    assert len(a.defrosts) == 2
    first = a.defrosts[0]
    assert abs(first.start - (START + timedelta(hours=6))) <= timedelta(minutes=4)
    assert first.seconds / 60 == pytest.approx(30, abs=4)
    assert first.peak == pytest.approx(12.0, abs=1)
    assert first.recovery_seconds / 60 == pytest.approx(8, abs=4)


def test_open_door_is_not_a_defrost():
    # The air shoots up but the evaporator stays cold: the compressor runs.
    chamber, evaporator = synthetic_day(doors=(5 * 60 + 2, 11 * 60 + 2))
    a = analyze_day(chamber, evaporator, START, END, cut_in=HIGH, cut_out=LOW)
    assert a.defrosts == []


def test_off_cycle_defrost_without_heater():
    # Display cases: the compressor just holds off, the coil warms with the air.
    chamber, evaporator = synthetic_day(defrosts=(8 * 60 + 2,))
    evaporator = [(t, min(e, c - 1.5)) for (t, e), (_, c) in zip(evaporator, chamber)]
    a = analyze_day(chamber, evaporator, START, END, cut_in=HIGH, cut_out=LOW)
    assert len(a.defrosts) == 1


def test_without_evaporator_a_towering_rise_is_a_defrost():
    chamber, _ = synthetic_day(defrosts=(6 * 60 + 2,))
    a = analyze_day(chamber, None, START, END)
    assert len(a.defrosts) == 1


def test_hours_of_warming_are_off_not_defrost():
    chamber, evaporator = synthetic_day(off=(10 * 60 + 2, 14 * 60))
    a = analyze_day(chamber, evaporator, START, END, cut_in=HIGH, cut_out=LOW)
    assert a.defrosts == []
    assert [r.kind for r in a.runs].count("off") == 1


def test_gap_splits_the_day_and_is_not_covered():
    chamber, evaporator = synthetic_day(gap=(600, 700))
    a = analyze_day(chamber, evaporator, START, END, cut_in=HIGH, cut_out=LOW)
    # The last value carries on for MAX_GAP (10 min) before the gap counts.
    assert a.covered_seconds == (24 * 60 - 100 + 10) * 60
    assert all(not (r.start < START + timedelta(minutes=650) < r.end) for r in a.runs)


def test_no_readings_gives_an_empty_day():
    a = analyze_day([], None, START, END)
    assert a.runs == [] and a.duty_percent is None and a.covered_seconds == 0


def test_day_bounds_and_next_run_follow_warsaw_midnight():
    assert day_bounds(date(2026, 10, 20)) == (START, END)
    # 25 hours on the day the clocks go back.
    s, e = day_bounds(date(2026, 10, 25))
    assert e - s == timedelta(hours=25)
    # 23:00 Warsaw → runs at 00:05, 65 minutes later.
    assert seconds_until_next_run(datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc)) == 65 * 60


@pytest.mark.asyncio
async def test_nightly_run_stores_reports_once_and_owner_reads_them(client, db_session, make_user):
    owner, stranger = await make_user(UserRole.USER), await make_user(UserRole.USER)
    obj = await make_object(db_session)
    await _assign(db_session, owner, obj)
    chamber_s = await _sensor(db_session, obj, "lada")
    evaporator_s = await _sensor(db_session, obj, "lada-parownik")
    chamber, evaporator = synthetic_day(defrosts=(6 * 60 + 2,))
    await _readings(db_session, chamber_s, chamber)
    await _readings(db_session, evaporator_s, evaporator)
    receiver = Receiver(
        name="Lada 2", object_id=obj.id, chamber_sensor_id=chamber_s.id,
        evaporator_sensor_id=evaporator_s.id, cut_in=HIGH, cut_out=LOW,
        created_at=START - timedelta(days=30),
    )
    db_session.add(receiver)
    await db_session.commit()

    # Run on 21.10: the last 7 days are due (no earlier receiver days skipped:
    # the receiver is older), only 20.10 has readings.
    assert await run_pending(db_session, today=date(2026, 10, 21)) == 7
    assert await run_pending(db_session, today=date(2026, 10, 21)) == 0

    resp = await client.get(f"/api/v1/objects/{obj.id}/reports/receivers", headers=auth_headers(owner))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["day"] == "2026-10-20"
    assert body["days"][0] == "2026-10-20" and len(body["days"]) == 7
    [report] = body["receivers"]
    assert report["name"] == "Lada 2"
    assert report["defrost_count"] == 1
    assert report["cooling_count"] > 80
    assert report["defrosts"][0]["peak"] == pytest.approx(12.0, abs=1)

    resp = await client.get(
        f"/api/v1/objects/{obj.id}/reports/receivers?day=2026-10-18", headers=auth_headers(owner)
    )
    [empty_day] = resp.json()["receivers"]
    assert empty_day["covered_seconds"] == 0

    resp = await client.get(f"/api/v1/objects/{obj.id}/reports/receivers", headers=auth_headers(stranger))
    assert resp.status_code == 404
