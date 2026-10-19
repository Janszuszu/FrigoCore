"""Readings a gateway buffered during an outage are replayed with their own
timestamp and quality STALE — they belong in the history at that time and
must never overwrite the sensor's live value."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.measurement import Measurement
from app.models.sensor import Sensor
from app.mqtt.client import MQTTEngine
from tests.helpers import make_object


def payload(value: float, at: datetime, quality: str = "GOOD") -> bytes:
    return json.dumps({"timestamp": at.isoformat(), "value": value, "temperature": value, "quality": quality}).encode()


def test_parse_payload_reads_timestamp_and_quality():
    at = datetime(2026, 10, 17, 2, 55, 20, tzinfo=timezone.utc)
    assert MQTTEngine._parse_payload(payload(1.447, at, "STALE")) == (1.447, at, True)
    assert MQTTEngine._parse_payload(b'{"temperature": 4.2}') == (4.2, None, False)
    assert MQTTEngine._parse_payload(b'{"temperature": 4.2, "timestamp": "nonsense"}') == (4.2, None, False)


async def _persist(session, topic, raw: bytes) -> None:
    value, measured_at, stale = MQTTEngine._parse_payload(raw)
    await MQTTEngine._persist_measurement(session, topic, value, measured_at=measured_at, stale=stale)
    await session.commit()


async def _sensor(session, topic: str) -> Sensor:
    obj = await make_object(session)
    sensor = Sensor(name="Komora", object_id=obj.id, mqtt_topic=topic)
    session.add(sensor)
    await session.commit()
    return sensor


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_replayed_reading_is_stored_at_its_time_and_leaves_live_state(db_session):
    sensor = await _sensor(db_session, "frigo/bf/komora")
    now = datetime.now(timezone.utc)
    await _persist(db_session, sensor.mqtt_topic, payload(2.5, now))
    old = now - timedelta(days=2)
    await _persist(db_session, sensor.mqtt_topic, payload(18.4, old, "STALE"))

    await db_session.refresh(sensor)
    assert sensor.current_temperature == 2.5
    assert _aware(sensor.last_message_at) >= now - timedelta(seconds=5)
    rows = (await db_session.execute(
        select(Measurement.temperature, Measurement.received_at).where(Measurement.sensor_id == sensor.id)
    )).all()
    stored = {t: _aware(at) for t, at in rows}
    assert abs(stored[18.4] - old) < timedelta(seconds=1)
    assert stored[2.5] >= now - timedelta(seconds=5)


@pytest.mark.asyncio
async def test_old_timestamp_without_stale_flag_is_also_backfill(db_session):
    sensor = await _sensor(db_session, "frigo/bf/lada")
    await _persist(db_session, sensor.mqtt_topic, payload(7.0, datetime.now(timezone.utc) - timedelta(hours=1)))
    await db_session.refresh(sensor)
    assert sensor.current_temperature is None


@pytest.mark.asyncio
async def test_live_and_untrusted_timestamps_are_stored_as_received(db_session):
    sensor = await _sensor(db_session, "frigo/bf/sklep")
    # A gateway booted without an RTC may send 1970 or a future clock.
    for at in (datetime(1970, 1, 1, tzinfo=timezone.utc), datetime.now(timezone.utc) + timedelta(days=1)):
        await _persist(db_session, sensor.mqtt_topic, payload(21.0, at))
    await db_session.refresh(sensor)
    assert sensor.current_temperature == 21.0
    rows = (await db_session.execute(select(Measurement.received_at).where(Measurement.sensor_id == sensor.id))).scalars().all()
    assert all(_aware(at) >= datetime.now(timezone.utc) - timedelta(minutes=1) for at in rows)
