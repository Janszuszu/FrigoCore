"""Demo feed — synthetic readings for sensors under the demo/ topic namespace."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.measurement import Measurement
from app.models.sensor import Sensor
from app.services.demo_feed import FREEZER, SIGNALS, feed_once, signal_for
from app.services.receiver_state import COOLING, IDLE, classify
from tests.helpers import make_object

T = 1_791_000_000.0  # any instant


def test_freezer_stays_between_its_cut_out_and_cut_in():
    values = [SIGNALS["1"](T + s) for s in range(0, 2 * FREEZER[0], 30)]
    assert min(values) >= FREEZER[3] - 0.01 and max(values) <= FREEZER[2] + 0.01


def test_energy_counter_only_grows_and_power_follows_the_compressors():
    readings = [SIGNALS["energia"](T + s) for s in range(0, 7200, 60)]
    assert all(b >= a for a, b in zip(readings, readings[1:]))
    assert {round(SIGNALS["moc"](T + s)) for s in range(0, 3600, 30)} >= {25, 975}


def test_receiver_state_reads_the_demo_freezer_as_cooling_then_idle():
    """The synthetic traces must drive the real state classifier sensibly."""
    period, cooling, _, _ = FREEZER
    start = T - (T % period)  # a cycle begins: compressor on

    def trace(signal, end):
        return [(datetime.fromtimestamp(end - 60 * (10 - i), timezone.utc), signal(end - 60 * (10 - i))) for i in range(11)]

    mid_cooling = start + cooling - 60
    mid_idle = start + period - 60
    for at, expected in ((mid_cooling, COOLING), (mid_idle, IDLE)):
        now = datetime.fromtimestamp(at, timezone.utc)
        assert classify(trace(SIGNALS["1"], at), trace(SIGNALS["mroznia-parownik"], at), now) == expected


def test_only_demo_topics_with_known_signals_are_fed():
    assert signal_for("demo/obiekt-demonstracyjny/1") is SIGNALS["1"]
    assert signal_for("demo/obiekt-demonstracyjny/nieznany") is None
    assert signal_for("frigo/lewiatan-gorowo/1") is None


@pytest.mark.asyncio
async def test_feed_fills_the_gap_and_leaves_real_sensors_alone(db_session):
    obj = await make_object(db_session)
    demo = Sensor(name="Mroźnia", object_id=obj.id, mqtt_topic="demo/x/1")
    real = Sensor(name="Mroźnia", object_id=obj.id, mqtt_topic="frigo/x/1")
    db_session.add_all([demo, real])
    await db_session.commit()
    now = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    db_session.add(Measurement(sensor_id=demo.id, temperature=-20.0, received_at=now - timedelta(minutes=10)))
    await db_session.commit()

    written = await feed_once(db_session, now)

    # Four back-filled at 2-minute steps after the last reading, then the one due now.
    assert written == 5
    count = await db_session.scalar(select(func.count()).where(Measurement.sensor_id == demo.id))
    assert count == 6
    assert await db_session.scalar(select(func.count()).where(Measurement.sensor_id == real.id)) == 0
    await db_session.refresh(demo)
    assert demo.current_temperature == round(SIGNALS["1"](now.timestamp()), 3)
