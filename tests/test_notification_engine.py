"""Unit tests for the Notification Engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.enums import AlarmStatus, AlarmType, NotificationChannel
from app.models.alarm import Alarm
from app.models.notification_endpoint import NotificationEndpoint
from app.services.notification_engine import (
    NotificationEngine,
    _build_alarm_payload,
)


# ---------------------------------------------------------------------------
# _build_alarm_payload
# ---------------------------------------------------------------------------

def test_build_alarm_payload() -> None:
    alarm = Alarm(
        id=uuid.uuid4(),
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        status=AlarmStatus.TRIGGERED,
        trigger_value=9.2,
        detected_at=datetime.fromisoformat("2026-07-27T10:00:00+00:00"),
        triggered_at=datetime.fromisoformat("2026-07-27T10:05:00+00:00"),
        description="High temperature alarm — current: 9.2°C",
        object_id=uuid.uuid4(),
        sensor_id=uuid.uuid4(),
    )

    payload = _build_alarm_payload(alarm)

    assert payload["alarm_type"] == "high_temperature"
    assert payload["status"] == "triggered"
    assert payload["trigger_value"] == 9.2
    assert payload["subject"] == "FrigoCore Alarm — HIGH_TEMPERATURE"
    assert payload["message"] == alarm.description
    assert "2026-07-27T10:00:00" in payload["detected_at"]


def test_build_alarm_payload_offline_no_triggered_at() -> None:
    alarm = Alarm(
        id=uuid.uuid4(),
        alarm_type=AlarmType.OFFLINE,
        status=AlarmStatus.PENDING,
        trigger_value=180.0,
        detected_at=datetime.now(timezone.utc),
        triggered_at=None,
        description="Sensor offline",
        object_id=uuid.uuid4(),
        sensor_id=uuid.uuid4(),
    )

    payload = _build_alarm_payload(alarm)
    assert payload["triggered_at"] is None
    assert payload["alarm_type"] == "offline"


# ---------------------------------------------------------------------------
# NotificationEngine dispatch (no-op — all handlers log, never throw)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_notification_empty_endpoints() -> None:
    alarm = Alarm(
        id=uuid.uuid4(),
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        status=AlarmStatus.TRIGGERED,
        trigger_value=8.0,
        detected_at=datetime.now(timezone.utc),
        triggered_at=datetime.now(timezone.utc),
        description="Test",
        object_id=uuid.uuid4(),
    )
    # Should not raise
    await NotificationEngine.send_alarm_notification(alarm, [])


@pytest.mark.asyncio
async def test_send_notification_disabled_endpoint() -> None:
    alarm = Alarm(
        id=uuid.uuid4(),
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        status=AlarmStatus.TRIGGERED,
        trigger_value=8.0,
        detected_at=datetime.now(timezone.utc),
        triggered_at=datetime.now(timezone.utc),
        description="Test",
        object_id=uuid.uuid4(),
    )
    endpoint = NotificationEndpoint(
        channel=NotificationChannel.TELEGRAM,
        config={"chat_id": "123"},
        is_enabled=False,
    )
    # Should not raise — silently skipped
    await NotificationEngine.send_alarm_notification(alarm, [endpoint])


@pytest.mark.asyncio
async def test_send_notification_telegram() -> None:
    alarm = _make_alarm()
    endpoint = NotificationEndpoint(
        channel=NotificationChannel.TELEGRAM,
        config={"chat_id": "123456"},
        is_enabled=True,
    )
    await NotificationEngine.send_alarm_notification(alarm, [endpoint])


@pytest.mark.asyncio
async def test_send_notification_fcm() -> None:
    alarm = _make_alarm()
    endpoint = NotificationEndpoint(
        channel=NotificationChannel.FCM,
        config={"device_token": "abc123"},
        is_enabled=True,
    )
    await NotificationEngine.send_alarm_notification(alarm, [endpoint])


@pytest.mark.asyncio
async def test_send_notification_email() -> None:
    alarm = _make_alarm()
    endpoint = NotificationEndpoint(
        channel=NotificationChannel.EMAIL,
        config={"to": ["ops@example.com"]},
        is_enabled=True,
    )
    await NotificationEngine.send_alarm_notification(alarm, [endpoint])


@pytest.mark.asyncio
async def test_send_notification_sms() -> None:
    alarm = _make_alarm()
    endpoint = NotificationEndpoint(
        channel=NotificationChannel.SMS,
        config={"phone_number": "+48123456789"},
        is_enabled=True,
    )
    await NotificationEngine.send_alarm_notification(alarm, [endpoint])


@pytest.mark.asyncio
async def test_send_notification_webhook() -> None:
    alarm = _make_alarm()
    endpoint = NotificationEndpoint(
        channel=NotificationChannel.WEBHOOK,
        config={"url": "https://hooks.example.com/alerts"},
        is_enabled=True,
    )
    await NotificationEngine.send_alarm_notification(alarm, [endpoint])


@pytest.mark.asyncio
async def test_send_notification_multiple_endpoints() -> None:
    alarm = _make_alarm()
    endpoints = [
        NotificationEndpoint(channel=NotificationChannel.TELEGRAM, config={"chat_id": "1"}, is_enabled=True),
        NotificationEndpoint(channel=NotificationChannel.WEBHOOK, config={"url": "https://example.com"}, is_enabled=True),
        NotificationEndpoint(channel=NotificationChannel.EMAIL, config={"to": ["x@x.com"]}, is_enabled=False),
    ]
    # Should dispatch only to enabled endpoints
    await NotificationEngine.send_alarm_notification(alarm, endpoints)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_alarm() -> Alarm:
    return Alarm(
        id=uuid.uuid4(),
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        status=AlarmStatus.TRIGGERED,
        trigger_value=8.5,
        detected_at=datetime.now(timezone.utc),
        triggered_at=datetime.now(timezone.utc),
        description="High temperature alarm",
        object_id=uuid.uuid4(),
    )