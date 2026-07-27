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
from app.models.notification_profile import NotificationProfile
from app.models.sensor import Sensor
from app.services.notification_engine import NotificationEngine

logger = logging.getLogger(__name__)

# Interval between alarm evaluation cycles (seconds)
EVALUATION_INTERVAL_SECONDS = 10


class AlarmEngine:
    """Periodic background task that evaluates sensor alarms."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Begin the periodic evaluation loop."""
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Alarm engine started (interval=%ds)", EVALUATION_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Cancel the evaluation loop."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Alarm engine stopped")

    async def _run_loop(self) -> None:
        """Main evaluation loop."""
        while True:
            try:
                await self._evaluate_all()
            except Exception:
                logger.exception("Alarm engine evaluation failed")
            await asyncio.sleep(EVALUATION_INTERVAL_SECONDS)

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    async def _evaluate_all(self) -> None:
        """Evaluate all active sensors against their alarm configs."""
        async with self._session_factory() as session:
            # 1. Process active sensors — create PENDING alarms if thresholds breached
            await self._process_sensors(session)

            # 2. Transition PENDING alarms to TRIGGERED when delay has elapsed
            await self._transition_pending_to_triggered(session)

            # 3. Auto-resolve alarms when condition has cleared
            await self._auto_resolve_alarms(session)

            await session.commit()

    # ------------------------------------------------------------------
    # Step 1 — Sensor evaluation
    # ------------------------------------------------------------------

    @staticmethod
    async def _process_sensors(session: AsyncSession) -> None:
        """Iterate over active sensors and evaluate each alarm config."""
        stmt = select(Sensor).where(Sensor.is_active == True)
        result = await session.execute(stmt)
        sensors = result.scalars().all()

        now = datetime.now(timezone.utc)

        for sensor in sensors:
            # Re-fetch sensor with its alarm_configs eagerly loaded
            await session.refresh(sensor, attribute_names=["alarm_configs", "object_id"])
            configs = sensor.alarm_configs

            if not configs:
                continue

            for config in configs:
                if not config.is_enabled:
                    continue

                # Skip if a PENDING or TRIGGERED alarm already exists for this sensor+type
                existing = await session.scalar(
                    select(Alarm).where(
                        Alarm.sensor_id == sensor.id,
                        Alarm.alarm_type == config.alarm_type,
                        Alarm.status.in_([AlarmStatus.PENDING, AlarmStatus.TRIGGERED]),
                    )
                )
                if existing is not None:
                    continue

                # Evaluate condition
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
                        elapsed = (now - sensor.last_message_at).total_seconds()
                        if elapsed > sensor.offline_timeout_seconds:
                            breached = True
                            trigger_value = elapsed

                if breached:
                    # Determine object_id from the sensor's parent
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
                    logger.info(
                        "Alarm PENDING — type=%s sensor=%s value=%s",
                        config.alarm_type,
                        sensor.slug,
                        trigger_value,
                    )

    # ------------------------------------------------------------------
    # Step 2 — PENDING → TRIGGERED
    # ------------------------------------------------------------------

    @staticmethod
    async def _transition_pending_to_triggered(session: AsyncSession) -> None:
        """Transition PENDING alarms whose trigger delay has elapsed to TRIGGERED."""
        now = datetime.now(timezone.utc)

        # Fetch all PENDING alarms with their sensor's alarm_config
        pending_alarms = await session.execute(
            select(Alarm).where(Alarm.status == AlarmStatus.PENDING)
        )
        for alarm in pending_alarms.scalars().all():
            await session.refresh(alarm, attribute_names=["sensor"])
            sensor = alarm.sensor
            if sensor is None:
                continue

            await session.refresh(sensor, attribute_names=["alarm_configs"])
            # Find matching config
            config = next(
                (c for c in sensor.alarm_configs if c.alarm_type == alarm.alarm_type),
                None,
            )
            if config is None:
                continue

            # Compute required delay
            delay_seconds = config.trigger_delay_seconds
            if alarm.alarm_type == AlarmType.OFFLINE:
                delay_seconds = sensor.offline_timeout_seconds + config.trigger_delay_seconds

            elapsed = (now - alarm.detected_at).total_seconds()
            if elapsed >= delay_seconds:
                alarm.status = AlarmStatus.TRIGGERED
                alarm.triggered_at = now
                session.add(alarm)
                logger.warning(
                    "Alarm TRIGGERED — type=%s sensor=%s value=%s",
                    alarm.alarm_type.value,
                    sensor.slug,
                    alarm.trigger_value,
                )

                # --- Send notification ---
                await _send_triggered_notification(session, alarm)

    # ------------------------------------------------------------------
    # Step 3 — Auto-resolve alarms
    # ------------------------------------------------------------------

    @staticmethod
    async def _auto_resolve_alarms(session: AsyncSession) -> None:
        """Resolve alarms whose condition has cleared.

        For HIGH/LOW — temperature is back within bounds.
        For OFFLINE — sensor received a message (last_message_at updated).
        """
        now = datetime.now(timezone.utc)

        # Only auto-resolve PENDING and TRIGGERED alarms
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

            resolved = False

            if alarm.alarm_type == AlarmType.HIGH_TEMPERATURE:
                if sensor.current_temperature is not None and alarm.trigger_value is not None:
                    # Resolve if temperature dropped below threshold (or equal)
                    if sensor.current_temperature <= alarm.trigger_value:
                        resolved = True

            elif alarm.alarm_type == AlarmType.LOW_TEMPERATURE:
                if sensor.current_temperature is not None and alarm.trigger_value is not None:
                    if sensor.current_temperature >= alarm.trigger_value:
                        resolved = True

            elif alarm.alarm_type == AlarmType.OFFLINE:
                if sensor.last_message_at is not None:
                    elapsed = (now - sensor.last_message_at).total_seconds()
                    if elapsed <= sensor.offline_timeout_seconds:
                        resolved = True

            if resolved:
                alarm.status = AlarmStatus.RESOLVED
                alarm.resolved_at = now
                session.add(alarm)
                logger.info(
                    "Alarm RESOLVED — type=%s sensor=%s",
                    alarm.alarm_type.value,
                    sensor.slug,
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_description(alarm_type: AlarmType, value: float | None) -> str:
    """Generate a human-readable description for the alarm."""
    if alarm_type == AlarmType.HIGH_TEMPERATURE:
        return f"High temperature alarm — current: {value}°C"
    if alarm_type == AlarmType.LOW_TEMPERATURE:
        return f"Low temperature alarm — current: {value}°C"
    if alarm_type == AlarmType.OFFLINE:
        return f"Sensor offline — no message received for {value:.0f}s"
    return f"Alarm type: {alarm_type}"


async def _send_triggered_notification(session: AsyncSession, alarm: Alarm) -> None:
    """Load the object's notification endpoints and dispatch the alarm."""
    from sqlalchemy import select as _select
    from app.models.object import Object  # noqa: PLC0415

    # Fetch the object with its notification profile and endpoints
    stmt = (
        _select(Object)
        .where(Object.id == alarm.object_id)
    )
    result = await session.execute(stmt)
    obj = result.scalar_one_or_none()

    if obj is None:
        logger.warning("Object not found for alarm notification — object_id=%s", alarm.object_id)
        return

    await session.refresh(obj, attribute_names=["notification_profile"])
    profile = obj.notification_profile

    if profile is None:
        logger.info("No notification profile for object=%s", obj.slug)
        return

    await session.refresh(profile, attribute_names=["endpoints"])
    endpoints = profile.endpoints

    await NotificationEngine.send_alarm_notification(alarm, endpoints)
