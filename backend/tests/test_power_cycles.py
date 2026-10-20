"""Aggregate day from the power draw (run / rest, starts, energy) and its report."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.enums import UserRole
from app.models.aggregate import Aggregate, AggregateSensor
from app.services.daily_reports import run_pending
from app.services.power_cycles import analyze_power, learn_threshold
from tests.conftest import auth_headers
from tests.helpers import make_object
from tests.test_receivers import _assign, _readings, _sensor

START = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)  # 20.10 00:00 in Warsaw
END = START + timedelta(days=1)
RUN_MIN, REST_MIN = 20, 4


def power_day(gap: tuple[int, int] | None = None, always_on: bool = False):
    """A reading every 10 s: runs of RUN_MIN minutes winding down from 1000 W
    to 450 W, rests of REST_MIN minutes at 46 W standby."""
    period = RUN_MIN + REST_MIN
    points = []
    for s in range(0, 24 * 3600, 10):
        m = s / 60
        if gap and gap[0] <= m < gap[1]:
            continue
        k = m % period
        if always_on or k < RUN_MIN:
            w = 1000 - 550 * (k / RUN_MIN)
        else:
            w = 46.0
        points.append((START + timedelta(seconds=s), w))
    return points


def test_runs_rests_starts_and_energy():
    a = analyze_power(power_day(), START, END)
    # 60 cycles a day; the run under way at midnight is not a start.
    assert a.starts == 59
    assert a.avg_run_seconds == pytest.approx(RUN_MIN * 60, abs=20)
    assert a.avg_idle_seconds == pytest.approx(REST_MIN * 60, abs=20)
    assert a.duty_percent == pytest.approx(100 * RUN_MIN / (RUN_MIN + REST_MIN), abs=1)
    # 20 min of 725 W average + 4 min of 46 W, 60 times.
    expected = 60 * (725 * RUN_MIN / 60 + 46 * REST_MIN / 60) / 1000
    assert a.energy_kwh == pytest.approx(expected, rel=0.02)
    assert a.avg_running_power == pytest.approx(725, rel=0.03)


def test_threshold_lands_between_standby_and_the_wind_down():
    # The running level spreads 450..1000 W; the cut must stay under it.
    cut = learn_threshold([w for _, w in power_day()])
    assert 46 < cut < 450


def test_running_all_day_is_one_run_and_no_starts():
    a = analyze_power(power_day(always_on=True), START, END)
    assert a.starts == 0
    assert a.duty_percent == 100.0


def test_gap_breaks_runs_and_is_not_covered():
    a = analyze_power(power_day(gap=(600, 700)), START, END)
    assert a.covered_seconds < (24 * 60 - 99) * 60
    gap_at = START + timedelta(minutes=650)
    assert all(not (r.start < gap_at < r.end) for r in a.runs)


def test_too_few_readings_give_an_empty_day():
    assert analyze_power(power_day()[:10], START, END).runs == []


@pytest.mark.asyncio
async def test_nightly_aggregate_report_and_api(client, db_session, make_user):
    owner = await make_user(UserRole.USER)
    obj = await make_object(db_session)
    await _assign(db_session, owner, obj)
    power = await _sensor(db_session, obj, "agregat-moc", kind="power")
    outdoor = await _sensor(db_session, obj, "zewn")
    await _readings(db_session, power, power_day())
    aggregate = Aggregate(name="Icool", object_id=obj.id, created_at=START - timedelta(days=30))
    aggregate.sensor_links = [
        AggregateSensor(sensor_id=outdoor.id, position=0),
        AggregateSensor(sensor_id=power.id, position=1),
    ]
    bare = Aggregate(name="Bez licznika", object_id=obj.id, created_at=START - timedelta(days=30))
    bare.sensor_links = [AggregateSensor(sensor_id=outdoor.id, position=0)]
    db_session.add_all([aggregate, bare])
    await db_session.commit()

    # Seven days for the aggregate with a power sensor, none for the bare one.
    assert await run_pending(db_session, today=date(2026, 10, 21)) == 7

    resp = await client.get(f"/api/v1/objects/{obj.id}/reports/receivers", headers=auth_headers(owner))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["day"] == "2026-10-20"
    assert body["receivers"] == []
    [report] = body["aggregates"]
    assert report["name"] == "Icool"
    assert report["source"] == "power"
    assert report["starts"] == 59
    assert report["energy_kwh"] > 10
