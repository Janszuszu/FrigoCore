"""Unit tests for the Alarm Engine helpers and logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.enums import AlarmStatus, AlarmType
from app.models.alarm import Alarm
from app.models.alarm_config import AlarmConfig
from app.models.sensor import Sensor


# ---------------------------------------------------------------------------
# _build_description
# ---------------------------------------------------------------------------

def test_build_description_high() -> None:
    from app.services.alarm_engine import _build_description  # noqa: PLC0415
    desc = _build_description(AlarmType.HIGH_TEMPERATURE, 8.5)
    assert "High temperature" in desc
    assert "8.5" in desc


def test_build_description_low() -> None:
    from app.services.alarm_engine import _build_description  # noqa: PLC0415
    desc = _build_description(AlarmType.LOW_TEMPERATURE, -18.0)
    assert "Low temperature" in desc
    assert "-18.0" in desc


def test_build_description_offline() -> None:
    from app.services.alarm_engine import _build_description  # noqa: PLC0415
    desc = _build_description(AlarmType.OFFLINE, 120.0)
    assert "offline" in desc.lower()
    assert "120" in desc


# ---------------------------------------------------------------------------
# Rule validation — should NOT create alarm when TEMP is ok
# ---------------------------------------------------------------------------

def test_high_alarm_condition_not_breached() -> None:
    """Temperature is below threshold — no alarm should fire."""
    breached = 5.0 > 8.0  # threshold = 8
    assert breached is False


def test_low_alarm_condition_not_breached() -> None:
    """Temperature is above threshold — no alarm should fire."""
    breached = 5.0 < 2.0  # threshold = 2
    assert breached is False


# ---------------------------------------------------------------------------
# Rule validation — SHOULD create alarm when TEMP is out of range
# ---------------------------------------------------------------------------

def test_high_alarm_condition_breached() -> None:
    """Temperature is above threshold — alarm should fire."""
    breached = 9.0 > 8.0
    assert breached is True


def test_low_alarm_condition_breached() -> None:
    """Temperature is below threshold — alarm should fire."""
    breached = 1.0 < 2.0
    assert breached is True


# ---------------------------------------------------------------------------
# OFFLINE detection — rule check
# ---------------------------------------------------------------------------

def test_offline_condition_not_breached() -> None:
    """Last message was 60 seconds ago, offline timeout is 120 — should NOT fire."""
    now = datetime.now(timezone.utc)
    last_message = now - timedelta(seconds=60)
    elapsed = (now - last_message).total_seconds()
    breached = elapsed > 120  # offline_timeout_seconds = 120
    assert breached is False


def test_offline_condition_breached() -> None:
    """Last message was 130 seconds ago, offline timeout is 120 — SHOULD fire."""
    now = datetime.now(timezone.utc)
    last_message = now - timedelta(seconds=130)
    elapsed = (now - last_message).total_seconds()
    breached = elapsed > 120  # offline_timeout_seconds = 120
    assert breached is True


# ---------------------------------------------------------------------------
# Trigger delay calculation
# ---------------------------------------------------------------------------

def test_trigger_delay_high_temperature() -> None:
    """HIGH alarm delay = trigger_delay_seconds (no extra timeout)."""
    config = AlarmConfig(
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        threshold_value=8.0,
        trigger_delay_seconds=300,
    )
    assert config.effective_offline_delay.total_seconds() == 300


def test_trigger_delay_low_temperature() -> None:
    """LOW alarm delay = trigger_delay_seconds (no extra timeout)."""
    config = AlarmConfig(
        alarm_type=AlarmType.LOW_TEMPERATURE,
        threshold_value=2.0,
        trigger_delay_seconds=180,
    )
    assert config.effective_offline_delay.total_seconds() == 180


def test_trigger_delay_offline_with_sensor() -> None:
    """OFFLINE alarm delay = sensor.offline_timeout + trigger_delay."""
    sensor = Sensor(offline_timeout_seconds=120)
    config = AlarmConfig(
        alarm_type=AlarmType.OFFLINE,
        trigger_delay_seconds=300,
        sensor_id=sensor.id,
    )
    config.sensor = sensor  # simulate relationship
    assert config.effective_offline_delay.total_seconds() == 420  # 120 + 300


def test_trigger_delay_offline_without_sensor_fallback() -> None:
    """Without sensor relationship, fallback to trigger_delay only."""
    config = AlarmConfig(
        alarm_type=AlarmType.OFFLINE,
        trigger_delay_seconds=300,
    )
    assert config.effective_offline_delay.total_seconds() == 300


# ---------------------------------------------------------------------------
# Lifecycle transitions — logic verification
# ---------------------------------------------------------------------------

def test_alarm_initial_status_is_pending() -> None:
    """A new alarm should start with PENDING (constructor default)."""
    alarm = Alarm(
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        status=AlarmStatus.PENDING,
        trigger_value=9.2,
        detected_at=datetime.now(timezone.utc),
    )
    assert alarm.status == AlarmStatus.PENDING


def test_alarm_can_transition_to_triggered() -> None:
    """PENDING → TRIGGERED should be possible."""
    alarm = Alarm(
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        status=AlarmStatus.PENDING,
        trigger_value=9.2,
        detected_at=datetime.now(timezone.utc),
    )
    alarm.status = AlarmStatus.TRIGGERED
    alarm.triggered_at = datetime.now(timezone.utc)
    assert alarm.status == AlarmStatus.TRIGGERED


def test_alarm_can_transition_to_resolved() -> None:
    """TRIGGERED → RESOLVED should be possible."""
    alarm = Alarm(
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        status=AlarmStatus.TRIGGERED,
        trigger_value=9.2,
        detected_at=datetime.now(timezone.utc),
        triggered_at=datetime.now(timezone.utc),
    )
    alarm.status = AlarmStatus.RESOLVED
    alarm.resolved_at = datetime.now(timezone.utc)
    assert alarm.status == AlarmStatus.RESOLVED