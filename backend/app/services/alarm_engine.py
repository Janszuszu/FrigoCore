"""FrigoCore — Alarm Engine.

Handles the full lifecycle of alarms:
  - HIGH temperature alarm
  - LOW temperature alarm
  - OFFLINE alarm (missing MQTT messages)

Lifecycle: PENDING → TRIGGERED → ACKNOWLEDGED → RESOLVED

The engine is invoked periodically (e.g. every 10 seconds) and:
  1. Evaluates each active sensor against its alarm configs.
  2. Creates PENDING alarms when thresholds are breached.
  3. Transitions PENDING → TRIGGERED after trigger_delay_seconds.
  4. Auto-resolves TRIGGERED alarms when the condition clears.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.enums import AlarmStatus, AlarmType
from app.models.alarm import Alarm
from app.models.alarm_config import AlarmConfig
from app.api.websocket import manager as ws_manager
from app.models.notification_profile import NotificationProfile
from app.models.sensor import Sensor
from app.schemas import AlarmResponse
from app.services.notification_engine import NotificationEngine

logger = logging.getLogger(__name__)

# Interval between alarm evaluation cycles (seconds)
EVALUATION_INTERVAL_SECONDS = 10


def _alarm_type_str(alarm: Alarm) -> str:
    """Return alarm_type as a plain string, regardless of SQL dialect storage."""
    return alarm.alarm_type.value if hasattr(alarm.alarm_type, "value") else str(alarm.alarm_type)


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware UTC. SQLite stores naive UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _alarm_payload(alarm: Alarm) -> dict:
    """Serialize an alarm to the same full shape the REST API returns.

    WS broadcasts must match AlarmResponse/AlarmItem exactly — a partial
    payload gets blindly merged over the frontend's cached alarm and
    clobbers fields (e.g. triggered_at) the client already had.
    """
    return AlarmResponse.model_validate(alarm).model_dump(mode="json")


class AlarmEngine:
    """Periodic background task that evaluates sensor alarms."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Alarm engine started (interval=%ds)", EVALUATION_INTERVAL_SECONDS)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Alarm engine stopped")

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._evaluate_all()
            except Exception:
                logger.exception("Alarm engine evaluation failed")
            await asyncio.sleep(EVALUATION_INTERVAL_SECONDS)

    async def _evaluate_all(self) -> None:
        async with self._session_factory() as session:
            await self._process_sensors(session)
            await self._transition_pending_to_triggered(session)
            await self._auto_resolve_alarms(session)
            await session.commit()

    # ------------------------------------------------------------------
    # Step 1 — Sensor evaluation
    # ------------------------------------------------------------------
    @staticmethod
    async def _process_sensors(session: AsyncSession) -> None:
        stmt = select(Sensor).where(Sensor.is_active == True)
        result = await session.execute(stmt)
        sensors = result.scalars().all()
        now = datetime.now(timezone.utc)

        for sensor in sensors:
            await session.refresh(sensor, attribute_names=["alarm_configs", "object_id"])
            configs = sensor.alarm_configs
            if not configs:
                continue

            for config in configs:
                if not config.is_enabled:
                    continue

                existing = await session.scalar(
                    select(Alarm).where(
                        Alarm.sensor_id == sensor.id,
                        Alarm.alarm_type == config.alarm_type,
                        Alarm.status.in_([AlarmStatus.PENDING, AlarmStatus.TRIGGERED]),
                    )
                )
                if existing is not None:
                    continue

                breached = False
                trigger_value = None

                if config.alarm_type == AlarmType.HIGH_TEMPERATURE:
                    if sensor.current_temperature is not None and config.threshold_value is not None:
                        if sensor.current_temperature > config.threshold_value:
                            breached = True
                            trigger_value = sensor.current_temperature
                elif config.alarm_type == AlarmType.LOW_TEMPERATURE:
                    if sensor.current_temperature is not None and config.threshold_value is not None:
                        if sensor.current_temperature < config.threshold_value:
                            breached = True
                            trigger_value = sensor.current_temperature
                elif config.alarm_type == AlarmType.OFFLINE:
                    if sensor.last_message_at is not None:
                        elapsed = (now - _ensure_utc(sensor.last_message_at)).total_seconds()
                        if elapsed > sensor.offline_timeout_seconds:
                            breached = True
                            trigger_value = elapsed

                if breached:
                    await session.refresh(sensor, attribute_names=["object_id"])
                    alarm = Alarm(
                        alarm_type=config.alarm_type,
                        status=AlarmStatus.PENDING,
                        trigger_value=trigger_value,
                        detected_at=now,
                        object_id=sensor.object_id,
                        sensor_id=sensor.id,
                        description=_build_description(config.alarm_type, trigger_value),
                    )
                    session.add(alarm)
                    await session.flush()  # populate id/created_at/updated_at before broadcasting
                    logger.info(
                        "Alarm PENDING — type=%s sensor=%s value=%s",
                        config.alarm_type, sensor.name, trigger_value,
                    )
                    await ws_manager.broadcast("alarm.pending", _alarm_payload(alarm))

    # ------------------------------------------------------------------
    # Step 2 — PENDING → TRIGGERED
    # ------------------------------------------------------------------
    @staticmethod
    async def _transition_pending_to_triggered(session: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        pending_alarms = await session.execute(
            select(Alarm).where(Alarm.status == AlarmStatus.PENDING)
        )
        for alarm in pending_alarms.scalars().all():
            await session.refresh(alarm, attribute_names=["sensor"])
            sensor = alarm.sensor
            if sensor is None:
                continue
            await session.refresh(sensor, attribute_names=["alarm_configs"])
            config = next(
                (c for c in sensor.alarm_configs if c.alarm_type == alarm.alarm_type), None
            )
            if config is None:
                continue

            delay_seconds = config.trigger_delay_seconds
            # OFFLINE uses sum of offline_timeout + trigger_delay
            alarm_type_str = _alarm_type_str(alarm)
            if alarm_type_str == AlarmType.OFFLINE.value:
                delay_seconds = sensor.offline_timeout_seconds + config.trigger_delay_seconds

            elapsed = (now - _ensure_utc(alarm.detected_at)).total_seconds()
            if elapsed >= delay_seconds:
                alarm.status = AlarmStatus.TRIGGERED
                alarm.triggered_at = now
                session.add(alarm)
                await session.flush()  # persist updated_at before broadcasting
                logger.warning(
                    "Alarm TRIGGERED — type=%s sensor=%s value=%s",
                    alarm_type_str, sensor.name, alarm.trigger_value,
                )
                await ws_manager.broadcast("alarm.triggered", _alarm_payload(alarm))
                await _send_triggered_notification(session, alarm)

    # ------------------------------------------------------------------
    # Step 3 — Auto-resolve alarms
    # ------------------------------------------------------------------
    @staticmethod
    async def _auto_resolve_alarms(session: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        alarms = await session.execute(
            select(Alarm).where(
                Alarm.status.in_([AlarmStatus.PENDING, AlarmStatus.TRIGGERED]),
            )
        )
        for alarm in alarms.scalars().all():
            await session.refresh(alarm, attribute_names=["sensor"])
            sensor = alarm.sensor
            if sensor is None:
                continue

            alarm_type_str = _alarm_type_str(alarm)
            await session.refresh(sensor, attribute_names=["alarm_configs"])
            config = next(
                (c for c in sensor.alarm_configs if c.alarm_type == alarm.alarm_type), None
            )
            if config is None:
                continue

            resolved = False
            if config.alarm_type == AlarmType.HIGH_TEMPERATURE:
                if sensor.current_temperature is not None and config.threshold_value is not None:
                    if sensor.current_temperature <= config.threshold_value:
                        resolved = True
            elif config.alarm_type == AlarmType.LOW_TEMPERATURE:
                if sensor.current_temperature is not None and config.threshold_value is not None:
                    if sensor.current_temperature >= config.threshold_value:
                        resolved = True
            elif config.alarm_type == AlarmType.OFFLINE:
                if sensor.last_message_at is not None:
                    elapsed = (now - _ensure_utc(sensor.last_message_at)).total_seconds()
                    if elapsed <= sensor.offline_timeout_seconds:
                        resolved = True

            if resolved:
                alarm.status = AlarmStatus.RESOLVED
                alarm.resolved_at = now
                session.add(alarm)
                await session.flush()  # persist updated_at before broadcasting
                logger.info("Alarm RESOLVED — type=%s sensor=%s", alarm_type_str, sensor.name)
                await ws_manager.broadcast("alarm.resolved", _alarm_payload(alarm))


def _build_description(alarm_type: AlarmType, value: float | None) -> str:
    if alarm_type == AlarmType.HIGH_TEMPERATURE:
        return f"High temperature alarm — current: {value}°C"
    if alarm_type == AlarmType.LOW_TEMPERATURE:
        return f"Low temperature alarm — current: {value}°C"
    if alarm_type == AlarmType.OFFLINE:
        return f"Sensor offline — no message received for {value:.0f}s"
    return f"Alarm type: {alarm_type}"


async def _send_triggered_notification(session: AsyncSession, alarm: Alarm) -> None:
    from app.models.object import Object  # noqa: PLC0415

    stmt = select(Object).where(Object.id == alarm.object_id)
    result = await session.execute(stmt)
    obj = result.scalar_one_or_none()
    if obj is None:
        logger.warning("Object not found for alarm notification — object_id=%s", alarm.object_id)
        return
    await session.refresh(obj, attribute_names=["notification_profile"])
    profile = obj.notification_profile
    if profile is None:
        logger.info("No notification profile for object=%s", obj.name)
        return
    await session.refresh(profile, attribute_names=["endpoints"])
    endpoints = profile.endpoints
    await NotificationEngine.send_alarm_notification(alarm, endpoints)