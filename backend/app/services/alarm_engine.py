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

from app.enums import AlarmEventType, AlarmStatus, AlarmType
from app.models.alarm import Alarm
from app.models.alarm_config import AlarmConfig
from app.api.websocket import manager as ws_manager
from app.models.notification_profile import NotificationProfile
from app.models.sensor import Sensor
from app.schemas import AlarmResponse
from app.sensor_kinds import DEFROST_TOPIC_SUFFIX, SensorKind, kind_info
from app.services.dispatch_service import notify_object_owners, record_event
from app.services.notification_engine import (
    CLIENT_ALARM_EVENT_RESOLVED,
    CLIENT_ALARM_EVENT_TRIGGERED,
    NotificationEngine,
)

logger = logging.getLogger(__name__)

# Interval between alarm evaluation cycles (seconds)
EVALUATION_INTERVAL_SECONDS = 10

# Alarms not yet closed: one per sensor + type, and all of them close
# themselves once the reading is back to normal.
OPEN_STATUSES = [
    AlarmStatus.PENDING,
    AlarmStatus.TRIGGERED,
    AlarmStatus.ACKNOWLEDGED,
    AlarmStatus.EN_ROUTE,
]

# A test alarm closes this long after the service accepted it, so the owner
# also gets the "Alarm zakończony" push and the whole chain is exercised.
TEST_ALARM_CLOSE_AFTER_ACCEPT_SECONDS = 60
# ...and this long after it was raised if nobody accepted it at all.
TEST_ALARM_MAX_AGE_SECONDS = 30 * 60


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

                # An alarm the service has taken on stays the one alarm for
                # this condition until it clears — no fresh alarm every
                # trigger delay while the technician is working on it.
                existing = await session.scalar(
                    select(Alarm).where(
                        Alarm.sensor_id == sensor.id,
                        Alarm.alarm_type == config.alarm_type,
                        Alarm.status.in_(OPEN_STATUSES),
                    )
                )
                if existing is not None:
                    continue

                breached = False
                trigger_value = None

                if config.alarm_type == AlarmType.HIGH_TEMPERATURE:
                    if sensor.current_temperature is not None and config.threshold_value is not None:
                        if sensor.current_temperature > config.threshold_value and not await _defrost_active(
                            session, sensor, now
                        ):
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
                        description=_build_description(config.alarm_type, trigger_value, sensor.kind),
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

            # The room warms up during a defrost by design: hold the alarm
            # and restart its delay, so it only fires if the temperature is
            # still too high a full delay after the defrost has ended.
            if alarm_type_str == AlarmType.HIGH_TEMPERATURE.value and await _defrost_active(
                session, sensor, now
            ):
                alarm.detected_at = now
                session.add(alarm)
                continue

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
                await record_event(session, alarm.id, AlarmEventType.ALARM_TRIGGERED)
                # A failing notification must not take the evaluation cycle
                # down with it: an exception here would skip auto-resolve and
                # the commit, so the alarm state changes made above would be
                # rolled back and re-attempted forever.
                try:
                    await _send_triggered_notification(session, alarm)
                except Exception:
                    logger.exception(
                        "Failed to dispatch notification for alarm %s", alarm.id
                    )
                await notify_object_owners(session, alarm, CLIENT_ALARM_EVENT_TRIGGERED)

    # ------------------------------------------------------------------
    # Step 3 — Auto-resolve alarms
    # ------------------------------------------------------------------
    @staticmethod
    async def _auto_resolve_alarms(session: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        alarms = await session.execute(
            select(Alarm).where(Alarm.status.in_(OPEN_STATUSES))
        )
        for alarm in alarms.scalars().all():
            alarm_type_str = _alarm_type_str(alarm)
            if alarm_type_str == AlarmType.TEST.value:
                if _test_alarm_done(alarm, now):
                    await _resolve(session, alarm, now, "Alarm testowy zakończony", alarm_type_str, "test")
                continue

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
                await _resolve(session, alarm, now, "Condition auto-cleared", alarm_type_str, sensor.name)


def _test_alarm_done(alarm: Alarm, now: datetime) -> bool:
    if alarm.en_route_at is not None:
        return (now - _ensure_utc(alarm.en_route_at)).total_seconds() >= TEST_ALARM_CLOSE_AFTER_ACCEPT_SECONDS
    return (now - _ensure_utc(alarm.detected_at)).total_seconds() >= TEST_ALARM_MAX_AGE_SECONDS


async def _resolve(
    session: AsyncSession, alarm: Alarm, now: datetime, message: str, alarm_type_str: str, label: str
) -> None:
    # A PENDING alarm that clears inside its delay was never announced to
    # the owner, so there is nothing to close out.
    was_announced = alarm.status != AlarmStatus.PENDING
    alarm.status = AlarmStatus.RESOLVED
    alarm.resolved_at = now
    session.add(alarm)
    await session.flush()  # persist updated_at before broadcasting
    logger.info("Alarm RESOLVED — type=%s sensor=%s", alarm_type_str, label)
    await ws_manager.broadcast("alarm.resolved", _alarm_payload(alarm))
    await record_event(session, alarm.id, AlarmEventType.ALARM_RESOLVED, message=message)
    if was_announced:
        await notify_object_owners(session, alarm, CLIENT_ALARM_EVENT_RESOLVED)


async def raise_test_alarm(session: AsyncSession, object_id) -> Alarm:
    """A TRIGGERED test alarm for the object, sent down exactly the path a
    real one takes: the object's notification channels (incl. voice calls)
    and its owners now, the technicians via the EscalationEngine's next
    cycle. The caller commits."""
    now = datetime.now(timezone.utc)
    alarm = Alarm(
        alarm_type=AlarmType.TEST,
        status=AlarmStatus.TRIGGERED,
        detected_at=now,
        triggered_at=now,
        object_id=object_id,
        sensor_id=None,
        description="Alarm testowy — sprawdzenie powiadomień",
    )
    session.add(alarm)
    await session.flush()
    await record_event(session, alarm.id, AlarmEventType.ALARM_TRIGGERED, message="Alarm testowy z panelu")
    await ws_manager.broadcast("alarm.triggered", _alarm_payload(alarm))
    try:
        await _send_triggered_notification(session, alarm)
    except Exception:
        logger.exception("Failed to dispatch notification for test alarm %s", alarm.id)
    await notify_object_owners(session, alarm, CLIENT_ALARM_EVENT_TRIGGERED)
    return alarm


def _topic_slug(topic: str) -> str:
    return topic.rsplit("/", 1)[-1]


async def _defrost_active(session: AsyncSession, sensor: Sensor, now: datetime) -> bool:
    """True when a fresh defrost sensor of the same object reports 1 and
    covers this temperature sensor (see DEFROST_TOPIC_SUFFIX). A defrost
    sensor that went silent never holds alarms back."""
    if sensor.kind != SensorKind.TEMPERATURE.value:
        return False
    slug = _topic_slug(sensor.mqtt_topic)
    defrost_sensors = await session.scalars(
        select(Sensor).where(
            Sensor.object_id == sensor.object_id,
            Sensor.kind == SensorKind.DEFROST.value,
            Sensor.is_active == True,
        )
    )
    for defrost in defrost_sensors:
        defrost_slug = _topic_slug(defrost.mqtt_topic)
        if not defrost_slug.endswith(DEFROST_TOPIC_SUFFIX):
            continue
        group = defrost_slug[: -len(DEFROST_TOPIC_SUFFIX)]
        if slug != group and not slug.startswith(group + "-"):
            continue
        if defrost.current_temperature is None or defrost.current_temperature < 0.5:
            continue
        if defrost.last_message_at is None:
            continue
        age = (now - _ensure_utc(defrost.last_message_at)).total_seconds()
        if age <= defrost.offline_timeout_seconds:
            return True
    return False


def _build_description(alarm_type: AlarmType, value: float | None, kind: str | None = None) -> str:
    info = kind_info(kind)
    if info.states is not None and alarm_type != AlarmType.OFFLINE:
        # On/off sensor: the value is just 0/1, the reason says it all.
        return info.high_reason if alarm_type == AlarmType.HIGH_TEMPERATURE else info.low_reason
    if alarm_type == AlarmType.HIGH_TEMPERATURE:
        return f"{info.high_reason} — aktualnie {value} {info.unit}"
    if alarm_type == AlarmType.LOW_TEMPERATURE:
        return f"{info.low_reason} — aktualnie {value} {info.unit}"
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
    await NotificationEngine.send_alarm_notification(alarm, endpoints, object_name=obj.name)