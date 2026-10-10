"""Sensor kinds — units in the API, unit-aware alarm wording, daily energy."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select

from app.api.routes import ENERGY_TIMEZONE
from app.enums import AlarmStatus, AlarmType, UserRole
from app.models.alarm import Alarm
from app.models.alarm_config import AlarmConfig
from app.models.measurement import Measurement
from app.models.object import Object
from app.models.sensor import Sensor
from app.database import async_session_factory
from app.services.alarm_engine import AlarmEngine
from app.services.notification_engine import build_client_alarm_payload, build_voice_message
from tests.conftest import auth_headers
from tests.helpers import make_object


@pytest.mark.asyncio
async def test_sensor_defaults_to_temperature_in_celsius(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    resp = await client.post(
        f"/api/v1/objects/{obj.id}/sensors",
        json={"name": "Komora", "mqtt_topic": "frigo/t/komora"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201
    assert resp.json()["kind"] == "temperature"
    assert resp.json()["unit"] == "°C"


@pytest.mark.asyncio
async def test_current_sensor_reports_amps(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    resp = await client.post(
        f"/api/v1/objects/{obj.id}/sensors",
        json={"name": "Agregat prąd", "mqtt_topic": "frigo/t/prad", "kind": "current", "icon": "compressor"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 201
    assert resp.json()["unit"] == "A"


@pytest.mark.asyncio
async def test_unknown_kind_is_rejected(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    resp = await client.post(
        f"/api/v1/objects/{obj.id}/sensors",
        json={"name": "X", "mqtt_topic": "frigo/t/x", "kind": "pressure"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_overcurrent_alarm_is_worded_in_amps(db_session):
    obj = await make_object(db_session, "Lewiatan")
    sensor = Sensor(
        name="Agregat prąd", mqtt_topic="frigo/t/prad", object_id=obj.id, kind="current",
        current_temperature=14.2, last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(sensor)
    await db_session.flush()
    db_session.add(AlarmConfig(
        alarm_type=AlarmType.HIGH_TEMPERATURE, threshold_value=10.0, trigger_delay_seconds=0,
        is_enabled=True, sensor_id=sensor.id,
    ))
    await db_session.commit()

    engine = AlarmEngine(async_session_factory)
    await engine._evaluate_all()
    await engine._evaluate_all()

    async with async_session_factory() as session:
        alarm = await session.scalar(select(Alarm).where(Alarm.sensor_id == sensor.id))
        assert alarm.status == AlarmStatus.TRIGGERED
        assert "Przeciążenie" in alarm.description
        assert "14.2 A" in alarm.description
        obj_row = await session.get(Object, obj.id)
        push = build_client_alarm_payload(alarm, obj_row, "triggered")
        voice = build_voice_message(alarm, obj_row.name)

    assert push["message"] == "Agregat prąd: Przeciążenie — wysoki prąd (14,2 A)"
    assert alarm.sensor_kind == "current" and alarm.sensor_unit == "A"
    assert "Przeciążenie — wysoki prąd, aktualnie 14,2 ampera." in voice
    assert "stopni" not in voice


def test_alarm_without_loaded_sensor_keeps_temperature_wording():
    alarm = Alarm(
        id=uuid.uuid4(), alarm_type=AlarmType.HIGH_TEMPERATURE, object_id=uuid.uuid4(),
        trigger_value=8.46, detected_at=datetime.now(timezone.utc), description="",
    )
    assert "Wysoka temperatura, aktualnie 8,5 stopni." in build_voice_message(alarm, "Chłodnia")


async def _energy_sensor(db, readings: list[tuple[datetime, float]]) -> Sensor:
    obj = await make_object(db)
    sensor = Sensor(name="Energia", mqtt_topic=f"frigo/t/{uuid.uuid4()}", object_id=obj.id, kind="energy")
    db.add(sensor)
    await db.flush()
    for at, kwh in readings:
        db.add(Measurement(sensor_id=sensor.id, temperature=kwh, received_at=at))
    await db.commit()
    return sensor


def _local(day_offset: int, hour: int) -> datetime:
    day = datetime.now(ENERGY_TIMEZONE).date() + timedelta(days=day_offset)
    return datetime.combine(day, time(hour), ENERGY_TIMEZONE).astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_energy_daily_uses_counter_movement_between_days(client, db_session, make_user):
    user = await make_user(UserRole.ADMIN)
    sensor = await _energy_sensor(db_session, [
        (_local(-2, 8), 100.0), (_local(-2, 20), 104.0),   # 4 kWh within the day
        (_local(-1, 8), 105.0), (_local(-1, 20), 110.5),   # 110.5 - 104.0 = 6.5
        (_local(0, 1), 111.0),                              # 111.0 - 110.5 = 0.5
    ])
    resp = await client.get(f"/api/v1/sensors/{sensor.id}/energy/daily?days=3", headers=auth_headers(user))
    assert resp.status_code == 200
    assert [d["kwh"] for d in resp.json()] == [4.0, 6.5, 0.5]


@pytest.mark.asyncio
async def test_energy_daily_survives_meter_reset(client, db_session, make_user):
    user = await make_user(UserRole.ADMIN)
    sensor = await _energy_sensor(db_session, [
        (_local(-1, 10), 500.0),
        (_local(0, 2), 0.2), (_local(0, 3), 1.2),  # meter replaced overnight
    ])
    resp = await client.get(f"/api/v1/sensors/{sensor.id}/energy/daily?days=2", headers=auth_headers(user))
    assert [d["kwh"] for d in resp.json()] == [0.0, 1.0]


@pytest.mark.asyncio
async def test_energy_daily_rejects_non_energy_sensor(client, db_session, make_user):
    user = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    sensor = Sensor(name="Komora", mqtt_topic="frigo/t/k", object_id=obj.id)
    db_session.add(sensor)
    await db_session.commit()
    resp = await client.get(f"/api/v1/sensors/{sensor.id}/energy/daily", headers=auth_headers(user))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_alarm_api_reports_sensor_unit(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    sensor = Sensor(name="Napięcie", mqtt_topic="frigo/t/v", object_id=obj.id, kind="voltage")
    db_session.add(sensor)
    await db_session.flush()
    db_session.add(Alarm(
        alarm_type=AlarmType.LOW_TEMPERATURE, status=AlarmStatus.TRIGGERED, trigger_value=198.0,
        detected_at=datetime.now(timezone.utc), description="", object_id=obj.id, sensor_id=sensor.id,
    ))
    await db_session.commit()
    resp = await client.get("/api/v1/alarms", headers=auth_headers(admin))
    alarm = resp.json()[0]
    assert alarm["sensor_kind"] == "voltage"
    assert alarm["sensor_unit"] == "V"
