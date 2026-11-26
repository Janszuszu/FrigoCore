"""Chamber door in the day report: openings and total open time."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.receiver import Receiver
from app.models.receiver_day_report import ReceiverDayReport
from app.services.daily_reports import run_pending
from app.services.door_stats import analyze_door, covers
from tests.conftest import auth_headers
from tests.helpers import make_object
from tests.test_receivers import _assign, _readings, _sensor
from app.enums import UserRole

START = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)  # 20.10 00:00 in Warsaw
END = START + timedelta(days=1)


def door_day(openings: list[tuple[int, int]], step_s: int = 10, gap: tuple[int, int] | None = None):
    """A reading every `step_s` seconds; open during [a, b) minutes of the day."""
    points = []
    t = START - timedelta(minutes=2)
    while t < END:
        m = (t - START).total_seconds() / 60
        if not (gap and gap[0] <= m < gap[1]):
            v = 1.0 if any(a <= m < b for a, b in openings) else 0.0
            points.append((t, v))
        t += timedelta(seconds=step_s)
    return points


def test_counts_openings_and_open_time():
    d = analyze_door(door_day([(60, 63), (600, 601), (900, 915)]), START, END)
    assert d.openings == 3
    assert d.open_seconds == pytest.approx((3 + 1 + 15) * 60, abs=30)


def test_closed_all_day():
    d = analyze_door(door_day([]), START, END)
    assert (d.openings, d.open_seconds) == (0, 0)


def test_open_across_midnight_counts_time_but_not_a_new_opening():
    d = analyze_door(door_day([(-5, 4)]), START, END)
    assert d.openings == 0
    assert d.open_seconds == pytest.approx(4 * 60, abs=20)


def test_silent_gateway_does_not_leave_the_door_open():
    # Last reading "open" at minute 100, then nothing for two hours.
    d = analyze_door(door_day([(95, 300)], gap=(100, 220)), START, END)
    # 5 min before the gap + at most 10 min credited to the last reading
    # + 80 min after it; the reading after the gap counts as a new opening.
    assert d.openings == 2
    assert d.open_seconds <= (5 + 10 + 80) * 60 + 30


def test_door_belongs_to_its_chamber_by_topic():
    assert covers("frigo/g/komora-drzwi", "frigo/g/komora")
    assert covers("frigo/g/komora-drzwi", "frigo/g/komora-parownik")
    assert not covers("frigo/g/komora-drzwi", "frigo/g/lada-1")
    assert not covers("frigo/g/komora-odszranianie", "frigo/g/komora")


@pytest.mark.asyncio
async def test_report_carries_door_figures_and_backfills_old_reports(client, db_session, make_user):
    owner = await make_user(UserRole.USER)
    obj = await make_object(db_session)
    await _assign(db_session, owner, obj)
    chamber = await _sensor(db_session, obj, "komora")
    lada = await _sensor(db_session, obj, "lada")
    await _readings(db_session, chamber, [(START + timedelta(minutes=m), 4.0) for m in range(0, 1440, 5)])
    await _readings(db_session, lada, [(START + timedelta(minutes=m), 4.0) for m in range(0, 1440, 5)])
    old = START - timedelta(days=30)
    db_session.add_all([
        Receiver(name="Chłodnia", object_id=obj.id, chamber_sensor_id=chamber.id, created_at=old),
        Receiver(name="Lada", object_id=obj.id, chamber_sensor_id=lada.id, created_at=old),
    ])
    await db_session.commit()

    # Reports written before the chamber had a door sensor...
    await run_pending(db_session, today=date(2026, 10, 21))
    reports = (await db_session.scalars(select(ReceiverDayReport))).all()
    assert reports and all(r.door_open_count is None for r in reports)

    # ...get the door's figures once it shows up.
    door = await _sensor(db_session, obj, "komora-drzwi", kind="door")
    await _readings(db_session, door, door_day([(60, 63), (900, 915)], step_s=30))
    await run_pending(db_session, today=date(2026, 10, 21))

    resp = await client.get(
        f"/api/v1/objects/{obj.id}/reports/receivers?day=2026-10-20", headers=auth_headers(owner)
    )
    by_name = {r["name"]: r for r in resp.json()["receivers"]}
    assert by_name["Chłodnia"]["door_open_count"] == 2
    assert by_name["Chłodnia"]["door_open_seconds"] == pytest.approx(18 * 60, abs=60)
    assert by_name["Lada"]["door_open_count"] is None
