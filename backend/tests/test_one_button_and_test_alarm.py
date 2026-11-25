"""One-button "PRZYJĄŁEM" flow and the admin "Test alarm" button.

An accepted alarm stays the single alarm for its condition and closes
itself once the reading is back to normal; a test alarm walks the same
path as a real one and closes itself a minute after it is accepted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.database import async_session_factory
from app.enums import AlarmStatus, AlarmType, DevicePlatform, UserRole
from app.models.alarm import Alarm
from app.models.alarm_config import AlarmConfig
from app.models.device_token import DeviceToken
from app.models.sensor import Sensor
from app.services.alarm_engine import AlarmEngine
from app.services.escalation_engine import EscalationEngine
from app.services.notification_engine import (
    CLIENT_ALARM_EVENT_EN_ROUTE,
    CLIENT_ALARM_EVENT_RESOLVED,
    CLIENT_ALARM_EVENT_TRIGGERED,
    build_client_alarm_payload,
    build_service_alarm_payload,
    build_voice_message,
)

from .conftest import auth_headers
from .helpers import make_object, make_policy

alarm_engine = AlarmEngine(async_session_factory)
escalation = EscalationEngine(async_session_factory)
OWNER_PUSH = "app.services.dispatch_service.NotificationEngine.send_owner_alarm_push"


async def _hot_sensor(db, obj) -> Sensor:
    sensor = Sensor(
        name="Komora", mqtt_topic="test/komora", object_id=obj.id,
        current_temperature=10.0, last_message_at=datetime.now(timezone.utc),
    )
    db.add(sensor)
    await db.flush()
    db.add(AlarmConfig(
        alarm_type=AlarmType.HIGH_TEMPERATURE, threshold_value=5.0, trigger_delay_seconds=0,
        is_enabled=True, sensor_id=sensor.id,
    ))
    await db.commit()
    return sensor


async def _alarms(object_id) -> list[Alarm]:
    async with async_session_factory() as session:
        return (await session.scalars(
            select(Alarm).where(Alarm.object_id == object_id).order_by(Alarm.created_at)
        )).all()


async def _set_temperature(sensor_id, value: float) -> None:
    async with async_session_factory() as session:
        sensor = await session.get(Sensor, sensor_id)
        sensor.current_temperature = value
        await session.commit()


@pytest.mark.asyncio
async def test_accepted_alarm_is_not_raised_again_and_closes_itself(client, db_session, make_user):
    tech = await make_user(UserRole.SERWISANT)
    owner = await make_user(UserRole.USER)
    obj = await make_object(db_session)
    await db_session.refresh(owner, attribute_names=["objects"])
    owner.objects.append(obj)
    db_session.add(DeviceToken(user_id=owner.id, fcm_token="owner", platform=DevicePlatform.ANDROID, is_active=True))
    await db_session.commit()
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": tech.id}], object_id=obj.id)
    sensor = await _hot_sensor(db_session, obj)

    with patch(OWNER_PUSH, new_callable=AsyncMock) as push:
        await alarm_engine._evaluate_all()
        await alarm_engine._evaluate_all()
        await escalation.run_once()
        [alarm] = await _alarms(obj.id)
        assert alarm.status == AlarmStatus.TRIGGERED

        resp = await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(tech))
        assert resp.json()["status"] == AlarmStatus.EN_ROUTE.value

        # Still too warm while the technician works on it: no second alarm.
        await alarm_engine._evaluate_all()
        await alarm_engine._evaluate_all()
        assert len(await _alarms(obj.id)) == 1

        await _set_temperature(sensor.id, 2.0)
        await alarm_engine._evaluate_all()

    [alarm] = await _alarms(obj.id)
    assert alarm.status == AlarmStatus.RESOLVED
    events = [call.args[3] for call in push.await_args_list]
    assert events == [CLIENT_ALARM_EVENT_TRIGGERED, CLIENT_ALARM_EVENT_EN_ROUTE, CLIENT_ALARM_EVENT_RESOLVED]


@pytest.mark.asyncio
async def test_test_alarm_reaches_technicians_and_owners_then_closes(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    tech = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session, "Lewiatan")
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": tech.id}], object_id=obj.id)

    with patch(OWNER_PUSH, new_callable=AsyncMock) as push, patch(
        "app.services.dispatch_service.NotificationEngine.send_service_alarm_dispatch", new_callable=AsyncMock
    ) as service_push:
        resp = await client.post(f"/api/v1/objects/{obj.id}/test-alarm", headers=auth_headers(admin))
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["alarm_type"] == "test"
        assert body["status"] == AlarmStatus.TRIGGERED.value

        # A second press while it is still open is refused.
        again = await client.post(f"/api/v1/objects/{obj.id}/test-alarm", headers=auth_headers(admin))
        assert again.status_code == 409

        await escalation.run_once()
        service_push.assert_awaited_once()

        resp = await client.post(f"/api/v1/alarms/{body['id']}/accept", headers=auth_headers(tech))
        assert resp.json()["status"] == AlarmStatus.EN_ROUTE.value

        # Not yet a minute after acceptance: stays open.
        await alarm_engine._evaluate_all()
        [alarm] = await _alarms(obj.id)
        assert alarm.status == AlarmStatus.EN_ROUTE

        async with async_session_factory() as session:
            stored = await session.get(Alarm, alarm.id)
            stored.en_route_at = datetime.now(timezone.utc) - timedelta(minutes=2)
            await session.commit()
        await alarm_engine._evaluate_all()

    [alarm] = await _alarms(obj.id)
    assert alarm.status == AlarmStatus.RESOLVED
    # No owner assigned in this test — owners' pushes are covered below.
    push.assert_not_awaited()


@pytest.mark.asyncio
async def test_unanswered_test_alarm_closes_after_half_an_hour(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    resp = await client.post(f"/api/v1/objects/{obj.id}/test-alarm", headers=auth_headers(admin))
    async with async_session_factory() as session:
        stored = await session.get(Alarm, uuid.UUID(resp.json()["id"]))
        stored.detected_at = datetime.now(timezone.utc) - timedelta(minutes=31)
        await session.commit()

    await alarm_engine._evaluate_all()
    [alarm] = await _alarms(obj.id)
    assert alarm.status == AlarmStatus.RESOLVED


@pytest.mark.asyncio
async def test_test_alarm_tells_owners(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    owner = await make_user(UserRole.USER)
    obj = await make_object(db_session)
    await db_session.refresh(owner, attribute_names=["objects"])
    owner.objects.append(obj)
    db_session.add(DeviceToken(user_id=owner.id, fcm_token="owner", platform=DevicePlatform.ANDROID, is_active=True))
    await db_session.commit()

    with patch(OWNER_PUSH, new_callable=AsyncMock) as push:
        resp = await client.post(f"/api/v1/objects/{obj.id}/test-alarm", headers=auth_headers(admin))
    assert resp.status_code == 201
    assert [call.args[3] for call in push.await_args_list] == [CLIENT_ALARM_EVENT_TRIGGERED]


@pytest.mark.asyncio
async def test_only_admin_can_raise_test_alarm(client, db_session, make_user):
    tech = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    resp = await client.post(f"/api/v1/objects/{obj.id}/test-alarm", headers=auth_headers(tech))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_test_alarm_wording(db_session):
    obj = await make_object(db_session, "Lewiatan Górowo")
    alarm = Alarm(
        alarm_type=AlarmType.TEST, status=AlarmStatus.TRIGGERED,
        detected_at=datetime.now(timezone.utc), object_id=obj.id,
        description="Alarm testowy — sprawdzenie powiadomień",
    )
    db_session.add(alarm)
    await db_session.commit()

    owner = build_client_alarm_payload(alarm, obj, CLIENT_ALARM_EVENT_TRIGGERED)
    assert owner["title"] == "Alarm testowy"
    assert owner["alarm_type"] == "TEST"
    assert build_client_alarm_payload(alarm, obj, CLIENT_ALARM_EVENT_EN_ROUTE)["title"] == "Serwis w trakcie realizacji"
    assert "Lewiatan Górowo" in build_voice_message(alarm, obj.name)
    assert "Alarm testowy" in build_voice_message(alarm, obj.name)

    class _Assignment:
        id = "a"
        tier = 1
        dispatched_at = datetime.now(timezone.utc)

    assert build_service_alarm_payload(alarm, obj, _Assignment())["title"] == "ALARM TESTOWY"
