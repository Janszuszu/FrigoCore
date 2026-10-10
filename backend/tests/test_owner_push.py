"""Owner-facing CLIENT_ALARM push — object owners (role `user`) are told
about alarms on their own objects, never about anyone else's."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.enums import AlarmType, DevicePlatform, UserRole
from app.models.device_token import DeviceToken
from app.models.user import User
from app.services.dispatch_service import notify_object_owners
from app.services.escalation_engine import EscalationEngine
from app.database import async_session_factory
from app.services.notification_engine import (
    CLIENT_ALARM_EVENT_EN_ROUTE,
    CLIENT_ALARM_EVENT_RESOLVED,
    CLIENT_ALARM_EVENT_TRIGGERED,
    build_client_alarm_payload,
)

from .conftest import auth_headers
from .helpers import make_object, make_policy, make_triggered_alarm

engine = EscalationEngine(async_session_factory)


async def _add_device(db, user: User, token: str) -> None:
    db.add(DeviceToken(user_id=user.id, fcm_token=token, platform=DevicePlatform.ANDROID, is_active=True))
    await db.commit()


async def _assign(db, user: User, obj) -> None:
    await db.refresh(user, attribute_names=["objects"])
    user.objects.append(obj)
    await db.commit()


def _pushed_tokens(mock: AsyncMock) -> list[str]:
    return [d.fcm_token for call in mock.await_args_list for d in call.args[2]]


@pytest.mark.asyncio
async def test_only_assigned_owner_devices_are_pushed(db_session, make_user):
    obj = await make_object(db_session, "Chłodnia A")
    other = await make_object(db_session, "Chłodnia B")
    owner = await make_user(UserRole.USER)
    stranger = await make_user(UserRole.USER)
    tech = await make_user(UserRole.SERWISANT)
    await _assign(db_session, owner, obj)
    await _assign(db_session, stranger, other)
    await _assign(db_session, tech, obj)
    await _add_device(db_session, owner, "owner-token")
    await _add_device(db_session, stranger, "stranger-token")
    await _add_device(db_session, tech, "tech-token")
    alarm = await make_triggered_alarm(db_session, obj.id)

    with patch(
        "app.services.dispatch_service.NotificationEngine.send_owner_alarm_push", new_callable=AsyncMock
    ) as push:
        await notify_object_owners(db_session, alarm, CLIENT_ALARM_EVENT_TRIGGERED)

    assert _pushed_tokens(push) == ["owner-token"]
    assert push.await_args.args[3] == CLIENT_ALARM_EVENT_TRIGGERED


@pytest.mark.asyncio
async def test_inactive_owner_is_not_pushed(db_session, make_user):
    obj = await make_object(db_session)
    owner = await make_user(UserRole.USER, is_active=False)
    await _assign(db_session, owner, obj)
    await _add_device(db_session, owner, "owner-token")
    alarm = await make_triggered_alarm(db_session, obj.id)

    with patch(
        "app.services.dispatch_service.NotificationEngine.send_owner_alarm_push", new_callable=AsyncMock
    ) as push:
        await notify_object_owners(db_session, alarm, CLIENT_ALARM_EVENT_TRIGGERED)

    push.assert_not_awaited()


@pytest.mark.asyncio
async def test_push_failure_does_not_raise(db_session, make_user):
    obj = await make_object(db_session)
    owner = await make_user(UserRole.USER)
    await _assign(db_session, owner, obj)
    await _add_device(db_session, owner, "owner-token")
    alarm = await make_triggered_alarm(db_session, obj.id)

    with patch(
        "app.services.dispatch_service.NotificationEngine.send_owner_alarm_push",
        new_callable=AsyncMock,
        side_effect=RuntimeError("firebase down"),
    ):
        await notify_object_owners(db_session, alarm, CLIENT_ALARM_EVENT_TRIGGERED)


@pytest.mark.asyncio
async def test_en_route_and_resolve_notify_owner(client, db_session, make_user):
    tech = await make_user(UserRole.SERWISANT)
    owner = await make_user(UserRole.USER)
    obj = await make_object(db_session)
    await _assign(db_session, owner, obj)
    await _add_device(db_session, owner, "owner-token")
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": tech.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    with patch(
        "app.services.dispatch_service.NotificationEngine.send_owner_alarm_push", new_callable=AsyncMock
    ) as push:
        await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(tech))
        assert (await client.post(f"/api/v1/alarms/{alarm.id}/en-route", headers=auth_headers(tech))).status_code == 200
        assert (await client.post(f"/api/v1/alarms/{alarm.id}/resolve", headers=auth_headers(tech))).status_code == 200

    events = [call.args[3] for call in push.await_args_list]
    assert events == [CLIENT_ALARM_EVENT_EN_ROUTE, CLIENT_ALARM_EVENT_RESOLVED]


@pytest.mark.asyncio
async def test_client_alarm_payload_shape(db_session):
    obj = await make_object(db_session, "Chłodnia A")
    alarm = await make_triggered_alarm(db_session, obj.id)

    payload = build_client_alarm_payload(alarm, obj, CLIENT_ALARM_EVENT_TRIGGERED)

    assert payload["type"] == "CLIENT_ALARM"
    assert payload["event"] == CLIENT_ALARM_EVENT_TRIGGERED
    assert payload["alarm_id"] == str(alarm.id)
    assert payload["site_name"] == "Chłodnia A"
    assert payload["alarm_type"] == AlarmType.HIGH_TEMPERATURE.value.upper()
    assert "Wysoka temperatura" in payload["message"]
    assert "12,0 °C" in payload["message"]
