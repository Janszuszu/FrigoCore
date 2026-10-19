"""Chart data endpoint — /sensors/{id}/measurements/aggregated."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.enums import AlarmType, UserRole
from app.models.alarm_config import AlarmConfig
from app.models.measurement import Measurement
from app.models.sensor import Sensor
from tests.conftest import auth_headers
from tests.helpers import make_object


@pytest.mark.asyncio
async def test_aggregated_keeps_extremes_newest_first(client, db_session, make_user):
    user = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    sensor = Sensor(name="Komora", mqtt_topic="frigo/t/agg", object_id=obj.id)
    db_session.add(sensor)
    await db_session.flush()
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    # 100 readings a minute apart around 4 °C, one spike to 12 °C and one dip to -3 °C.
    for i in range(100):
        value = 12.0 if i == 30 else -3.0 if i == 70 else 4.0 + (i % 3) * 0.1
        db_session.add(Measurement(sensor_id=sensor.id, temperature=value, received_at=start + timedelta(minutes=i)))
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/sensors/{sensor.id}/measurements/aggregated",
        params={"since": (start - timedelta(minutes=1)).isoformat(), "target_points": 20},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    points = resp.json()
    assert len(points) <= 22
    values = [p["temperature"] for p in points]
    assert 12.0 in values and -3.0 in values
    times = [p["received_at"] for p in points]
    assert times == sorted(times, reverse=True)
    assert {"id", "temperature", "received_at", "sensor_id"} <= points[0].keys()
    assert points[0]["sensor_id"] == str(sensor.id)


@pytest.mark.asyncio
async def test_aggregated_returns_a_small_window_whole(client, db_session, make_user):
    user = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    sensor = Sensor(name="Komora", mqtt_topic="frigo/t/few", object_id=obj.id)
    db_session.add(sensor)
    await db_session.flush()
    start = datetime.now(timezone.utc) - timedelta(minutes=30)
    for i in range(15):
        db_session.add(Measurement(sensor_id=sensor.id, temperature=float(i), received_at=start + timedelta(minutes=i)))
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/sensors/{sensor.id}/measurements/aggregated",
        params={"since": (start - timedelta(minutes=1)).isoformat(), "target_points": 20},
        headers=auth_headers(user),
    )
    assert [p["temperature"] for p in resp.json()] == [float(i) for i in reversed(range(15))]


@pytest.mark.asyncio
async def test_alarm_limits_report_enabled_thresholds(client, db_session, make_user):
    user = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    sensor = Sensor(name="Komora", mqtt_topic="frigo/t/limits", object_id=obj.id)
    db_session.add(sensor)
    await db_session.flush()
    db_session.add_all([
        AlarmConfig(sensor_id=sensor.id, alarm_type=AlarmType.LOW_TEMPERATURE, threshold_value=-2.0),
        AlarmConfig(sensor_id=sensor.id, alarm_type=AlarmType.HIGH_TEMPERATURE, threshold_value=8.0),
        AlarmConfig(sensor_id=sensor.id, alarm_type=AlarmType.HIGH_TEMPERATURE, threshold_value=20.0, is_enabled=False),
        AlarmConfig(sensor_id=sensor.id, alarm_type=AlarmType.OFFLINE),
    ])
    await db_session.commit()

    resp = await client.get(f"/api/v1/sensors/{sensor.id}/alarm-limits", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json() == {"low": -2.0, "high": 8.0}


@pytest.mark.asyncio
async def test_alarm_limits_empty_without_thresholds(client, db_session, make_user):
    user = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    sensor = Sensor(name="Komora", mqtt_topic="frigo/t/nolimits", object_id=obj.id)
    db_session.add(sensor)
    await db_session.commit()

    resp = await client.get(f"/api/v1/sensors/{sensor.id}/alarm-limits", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json() == {"low": None, "high": None}
