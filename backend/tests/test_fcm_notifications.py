"""Real Firebase Cloud Messaging integration.

Covers the firebase_client initialization layer and the notification_engine
FCM send paths in isolation from the alarm state machine — Firebase itself
is always mocked, never touched for real.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from firebase_admin import exceptions as firebase_exceptions
from firebase_admin import messaging as fcm_messaging

from app.enums import AlarmType, DevicePlatform
from app.models.alarm import Alarm
from app.models.alarm_assignment import AlarmAssignment
from app.models.device_token import DeviceToken
from app.models.object import Object as ObjModel
from app.services import firebase_client
from app.services.firebase_client import FcmSendResult, FirebaseNotConfiguredError
from app.services.notification_engine import (
    NotificationEngine,
    SERVICE_ALARM_PAYLOAD_VERSION,
    build_service_alarm_payload,
)


@pytest.fixture(autouse=True)
def _reset_firebase_singleton():
    """firebase_client._app is a module-level singleton — isolate tests."""
    firebase_client._app = None
    yield
    firebase_client._app = None


def _make_alarm() -> Alarm:
    return Alarm(
        id=uuid.uuid4(),
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        object_id=uuid.uuid4(),
        detected_at=datetime.now(timezone.utc),
        description="Temperatura powyżej progu",
    )


def _make_object() -> ObjModel:
    return ObjModel(id=uuid.uuid4(), name="Chłodnia A")


def _make_assignment(alarm: Alarm) -> AlarmAssignment:
    return AlarmAssignment(
        id=uuid.uuid4(),
        alarm_id=alarm.id,
        tier=1,
        dispatched_at=datetime.now(timezone.utc),
    )


def _make_device(user_id=None, token="fcm-token-1", is_active=True) -> DeviceToken:
    return DeviceToken(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        fcm_token=token,
        platform=DevicePlatform.ANDROID,
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# 1. Firebase initialization
# ---------------------------------------------------------------------------


def test_get_firebase_app_initializes_exactly_once(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "FIREBASE_CREDENTIALS_PATH", "fake-creds.json")
    fake_app = MagicMock(name="FirebaseApp")

    with patch("app.services.firebase_client.credentials.Certificate") as mock_cert, patch(
        "app.services.firebase_client.firebase_admin.initialize_app", return_value=fake_app
    ) as mock_init, patch("app.services.firebase_client.firebase_admin._apps", {}):
        app1 = firebase_client.get_firebase_app()
        app2 = firebase_client.get_firebase_app()

    assert app1 is fake_app
    assert app2 is fake_app
    mock_init.assert_called_once()
    mock_cert.assert_called_once_with("fake-creds.json")


# ---------------------------------------------------------------------------
# 2. Missing credentials/configuration
# ---------------------------------------------------------------------------


def test_missing_credentials_path_raises_clearly(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "FIREBASE_CREDENTIALS_PATH", "")

    with patch("app.services.firebase_client.firebase_admin._apps", {}):
        with pytest.raises(FirebaseNotConfiguredError):
            firebase_client.get_firebase_app()


def test_invalid_credentials_file_raises_clearly(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "FIREBASE_CREDENTIALS_PATH", "does-not-exist.json")

    with patch("app.services.firebase_client.firebase_admin._apps", {}):
        with pytest.raises(FirebaseNotConfiguredError):
            firebase_client.get_firebase_app()


@pytest.mark.asyncio
async def test_dispatch_raises_when_firebase_not_configured(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "FIREBASE_CREDENTIALS_PATH", "")

    alarm = _make_alarm()
    obj = _make_object()
    assignment = _make_assignment(alarm)
    device = _make_device()

    with patch("app.services.firebase_client.firebase_admin._apps", {}):
        with pytest.raises(FirebaseNotConfiguredError):
            await NotificationEngine.send_service_alarm_dispatch(alarm, obj, assignment, [device])

    # Must not pretend the token was delivered or deactivated.
    assert device.is_active is True


# ---------------------------------------------------------------------------
# 3-4. Successful FCM send / multiple device tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_send_to_single_device():
    alarm = _make_alarm()
    obj = _make_object()
    assignment = _make_assignment(alarm)
    device = _make_device(token="good-token")

    with patch.object(firebase_client, "get_firebase_app", return_value=MagicMock()), patch.object(
        fcm_messaging, "send", return_value="projects/x/messages/1"
    ) as mock_send:
        await NotificationEngine.send_service_alarm_dispatch(alarm, obj, assignment, [device])

    mock_send.assert_called_once()
    assert device.is_active is True


@pytest.mark.asyncio
async def test_multiple_device_tokens_all_receive_send():
    alarm = _make_alarm()
    obj = _make_object()
    assignment = _make_assignment(alarm)
    user_id = uuid.uuid4()
    devices = [
        _make_device(user_id=user_id, token="phone-token"),
        _make_device(user_id=user_id, token="tablet-token"),
    ]

    with patch.object(firebase_client, "get_firebase_app", return_value=MagicMock()), patch.object(
        fcm_messaging, "send", return_value="ok"
    ) as mock_send:
        await NotificationEngine.send_service_alarm_dispatch(alarm, obj, assignment, devices)

    assert mock_send.call_count == 2
    sent_tokens = {call.args[0].token for call in mock_send.call_args_list}
    assert sent_tokens == {"phone-token", "tablet-token"}


# ---------------------------------------------------------------------------
# 5-6. One invalid token among many / deactivation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_invalid_token_does_not_block_the_others():
    alarm = _make_alarm()
    obj = _make_object()
    assignment = _make_assignment(alarm)
    good = _make_device(token="valid-token")
    bad = _make_device(token="stale-token")

    def _send_side_effect(message, app=None):
        if message.token == "stale-token":
            raise fcm_messaging.UnregisteredError("token no longer registered")
        return "ok"

    with patch.object(firebase_client, "get_firebase_app", return_value=MagicMock()), patch.object(
        fcm_messaging, "send", side_effect=_send_side_effect
    ) as mock_send:
        await NotificationEngine.send_service_alarm_dispatch(alarm, obj, assignment, [good, bad])

    assert mock_send.call_count == 2
    assert good.is_active is True
    assert bad.is_active is False


@pytest.mark.asyncio
async def test_invalid_token_deactivated_via_send_to_token():
    with patch.object(firebase_client, "get_firebase_app", return_value=MagicMock()), patch.object(
        fcm_messaging, "send", side_effect=fcm_messaging.UnregisteredError("gone")
    ):
        result = firebase_client.send_to_token("dead-token", {"type": "SERVICE_ALARM"})

    assert result == FcmSendResult.INVALID_TOKEN


@pytest.mark.asyncio
async def test_generic_fcm_error_does_not_deactivate_token():
    alarm = _make_alarm()
    obj = _make_object()
    assignment = _make_assignment(alarm)
    device = _make_device(token="flaky-token")

    with patch.object(firebase_client, "get_firebase_app", return_value=MagicMock()), patch.object(
        fcm_messaging, "send", side_effect=firebase_exceptions.FirebaseError("internal", "boom")
    ):
        await NotificationEngine.send_service_alarm_dispatch(alarm, obj, assignment, [device])

    # A transient error is not proof the token is invalid — must not deactivate.
    assert device.is_active is True


@pytest.mark.asyncio
async def test_inactive_tokens_are_skipped_without_calling_fcm():
    alarm = _make_alarm()
    obj = _make_object()
    assignment = _make_assignment(alarm)
    inactive = _make_device(token="already-inactive", is_active=False)

    with patch.object(fcm_messaging, "send") as mock_send:
        await NotificationEngine.send_service_alarm_dispatch(alarm, obj, assignment, [inactive])

    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# 7. SERVICE_ALARM payload shape is unchanged
# ---------------------------------------------------------------------------


def test_service_alarm_payload_shape_unchanged():
    alarm = _make_alarm()
    obj = _make_object()
    assignment = _make_assignment(alarm)

    payload = build_service_alarm_payload(alarm, obj, assignment)

    assert payload["type"] == "SERVICE_ALARM"
    assert payload["version"] == SERVICE_ALARM_PAYLOAD_VERSION
    assert payload["alarm_id"] == str(alarm.id)
    assert payload["assignment_id"] == str(assignment.id)
    assert payload["tier"] == 1
    assert payload["site_id"] == str(obj.id)
    assert payload["site_name"] == obj.name
    assert payload["severity"] == "CRITICAL"
    assert payload["requires_action"] is True
    assert payload["sensor_name"] == ""  # alarm.sensor never loaded in this fixture
    assert payload["dispatched_at"] == assignment.dispatched_at.isoformat()
    assert set(payload.keys()) == {
        "type",
        "version",
        "alarm_id",
        "assignment_id",
        "tier",
        "site_id",
        "site_name",
        "alarm_type",
        "severity",
        "title",
        "message",
        "sensor_name",
        "requires_action",
        "created_at",
        "dispatched_at",
    }
