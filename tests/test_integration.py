"""Integration tests for the full alarm pipeline.

Each test creates its own in-memory SQLite database — no external infra needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.enums import AlarmStatus, AlarmType, NotificationChannel
from app.models.alarm import Alarm
from app.models.alarm_config import AlarmConfig
from app.models.base import Base
from app.models.measurement import Measurement
from app.models.notification_endpoint import NotificationEndpoint
from app.models.object import Object
from app.models.sensor import Sensor
from app.services.alarm_engine import AlarmEngine, _build_description
from app.services.notification_engine import NotificationEngine


# ---------------------------------------------------------------------------
# Helpers — create a fresh in-memory session factory per test
# ---------------------------------------------------------------------------

async def _fresh_session_factory():
    """Return an async_sessionmaker bound to a fresh in-memory SQLite DB."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False), engine


async def _seed_object(session: AsyncSession) -> Object:
    obj = Object(name="Test Object")
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def _seed_sensor(
    session: AsyncSession,
    obj: Object,
    mqtt_topic: str = "test/sensor-1",
    offline_timeout: int = 120,
    initial_temp: float | None = None,
    last_message_offset_s: int | None = None,
) -> Sensor:
    lm = datetime.now(timezone.utc) - timedelta(seconds=last_message_offset_s) if last_message_offset_s else datetime.now(timezone.utc)
    sensor = Sensor(
        name="Test Sensor", mqtt_topic=mqtt_topic, object_id=obj.id,
        offline_timeout_seconds=offline_timeout,
        current_temperature=initial_temp,
        last_message_at=lm,
    )
    session.add(sensor)
    await session.commit()
    await session.refresh(sensor)
    return sensor


async def _seed_alarm_config(
    session: AsyncSession, sensor: Sensor, alarm_type: AlarmType,
    threshold: float | None = None, delay: int = 300,
) -> AlarmConfig:
    config = AlarmConfig(
        sensor_id=sensor.id, alarm_type=alarm_type,
        threshold_value=threshold, trigger_delay_seconds=delay,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


# ======================================================================
# Tests
# ======================================================================

@pytest.mark.asyncio
async def test_measurement_ingestion():
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj, last_message_offset_s=30)
            now = datetime.now(timezone.utc)
            m = Measurement(sensor_id=sensor.id, temperature=4.5, received_at=now)
            session.add(m)
            sensor.current_temperature = 4.5
            sensor.last_message_at = now
            session.add(sensor)
            await session.commit()
            await session.refresh(sensor)
            assert sensor.current_temperature == 4.5
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_high_alarm_created():
    factory, engine = await _fresh_session_factory()
    try:
        ae = AlarmEngine(factory)
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj, initial_temp=9.0, last_message_offset_s=5)
            await _seed_alarm_config(session, sensor, AlarmType.HIGH_TEMPERATURE, threshold=8.0)

        await ae._evaluate_all()

        async with factory() as session:
            result = await session.execute(
                select(Alarm).where(Alarm.sensor_id == sensor.id, Alarm.alarm_type == AlarmType.HIGH_TEMPERATURE)
            )
            alarm = result.scalar_one_or_none()
            assert alarm is not None
            assert alarm.status == AlarmStatus.PENDING
            assert alarm.trigger_value == 9.0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_high_alarm_not_created():
    factory, engine = await _fresh_session_factory()
    try:
        ae = AlarmEngine(factory)
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj, initial_temp=5.0, last_message_offset_s=5)
            await _seed_alarm_config(session, sensor, AlarmType.HIGH_TEMPERATURE, threshold=8.0)

        await ae._evaluate_all()

        async with factory() as session:
            result = await session.execute(select(Alarm).where(Alarm.sensor_id == sensor.id))
            assert len(result.scalars().all()) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_low_alarm_created():
    factory, engine = await _fresh_session_factory()
    try:
        ae = AlarmEngine(factory)
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj, initial_temp=1.0, last_message_offset_s=5)
            await _seed_alarm_config(session, sensor, AlarmType.LOW_TEMPERATURE, threshold=2.0)

        await ae._evaluate_all()

        async with factory() as session:
            result = await session.execute(
                select(Alarm).where(Alarm.sensor_id == sensor.id, Alarm.alarm_type == AlarmType.LOW_TEMPERATURE)
            )
            alarm = result.scalar_one_or_none()
            assert alarm is not None
            assert alarm.status == AlarmStatus.PENDING
            assert alarm.trigger_value == 1.0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_alarm_transitions_to_triggered():
    factory, engine = await _fresh_session_factory()
    try:
        ae = AlarmEngine(factory)
        now = datetime.now(timezone.utc)
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj, initial_temp=10.0, last_message_offset_s=5)
            await _seed_alarm_config(session, sensor, AlarmType.HIGH_TEMPERATURE, threshold=8.0)
            alarm = Alarm(
                alarm_type=AlarmType.HIGH_TEMPERATURE, status=AlarmStatus.PENDING,
                trigger_value=10.0, detected_at=now - timedelta(seconds=301),
                object_id=obj.id, sensor_id=sensor.id, description="Test",
            )
            session.add(alarm)
            await session.commit()

        await ae._evaluate_all()

        async with factory() as session:
            result = await session.execute(select(Alarm).where(Alarm.sensor_id == sensor.id))
            alarm = result.scalar_one()
            assert alarm.status == AlarmStatus.TRIGGERED
            assert alarm.triggered_at is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_high_alarm_cancelled_when_temp_recovers():
    factory, engine = await _fresh_session_factory()
    try:
        ae = AlarmEngine(factory)
        now = datetime.now(timezone.utc)
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj, initial_temp=7.0, last_message_offset_s=5)
            await _seed_alarm_config(session, sensor, AlarmType.HIGH_TEMPERATURE, threshold=8.0)
            alarm = Alarm(
                alarm_type=AlarmType.HIGH_TEMPERATURE, status=AlarmStatus.PENDING,
                trigger_value=9.5, detected_at=now - timedelta(seconds=60),
                object_id=obj.id, sensor_id=sensor.id, description="Test",
            )
            session.add(alarm)
            await session.commit()

        await ae._evaluate_all()

        async with factory() as session:
            result = await session.execute(select(Alarm).where(Alarm.sensor_id == sensor.id))
            alarm = result.scalar_one()
            assert alarm.status == AlarmStatus.RESOLVED
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_offline_alarm_created():
    factory, engine = await _fresh_session_factory()
    try:
        ae = AlarmEngine(factory)
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj, offline_timeout=120, last_message_offset_s=200)
            await _seed_alarm_config(session, sensor, AlarmType.OFFLINE, delay=300)

        await ae._evaluate_all()

        async with factory() as session:
            result = await session.execute(
                select(Alarm).where(Alarm.sensor_id == sensor.id, Alarm.alarm_type == AlarmType.OFFLINE)
            )
            alarm = result.scalar_one_or_none()
            assert alarm is not None
            assert alarm.status == AlarmStatus.PENDING
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_offline_alarm_not_created():
    factory, engine = await _fresh_session_factory()
    try:
        ae = AlarmEngine(factory)
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj, offline_timeout=120, last_message_offset_s=60)
            await _seed_alarm_config(session, sensor, AlarmType.OFFLINE, delay=300)

        await ae._evaluate_all()

        async with factory() as session:
            result = await session.execute(select(Alarm).where(Alarm.sensor_id == sensor.id))
            assert len(result.scalars().all()) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_acknowledge_alarm():
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj)
            alarm = Alarm(
                alarm_type=AlarmType.HIGH_TEMPERATURE, status=AlarmStatus.TRIGGERED,
                trigger_value=9.0, detected_at=datetime.now(timezone.utc),
                triggered_at=datetime.now(timezone.utc),
                object_id=obj.id, sensor_id=sensor.id, description="Test",
            )
            session.add(alarm)
            await session.commit()

            alarm.status = AlarmStatus.ACKNOWLEDGED
            alarm.acknowledged_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(alarm)
            assert alarm.status == AlarmStatus.ACKNOWLEDGED
            assert alarm.acknowledged_at is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_notification_dispatch_all_channels():
    alarm = Alarm(
        id=uuid.uuid4(), alarm_type=AlarmType.HIGH_TEMPERATURE,
        status=AlarmStatus.TRIGGERED, trigger_value=8.5,
        detected_at=datetime.now(timezone.utc), triggered_at=datetime.now(timezone.utc),
        description="Test alarm", object_id=uuid.uuid4(), sensor_id=uuid.uuid4(),
    )
    endpoints = [
        NotificationEndpoint(channel=NotificationChannel.TELEGRAM, config={"chat_id": "t1"}, is_enabled=True),
        NotificationEndpoint(channel=NotificationChannel.FCM, config={"device_token": "d1"}, is_enabled=True),
        NotificationEndpoint(channel=NotificationChannel.EMAIL, config={"to": ["x@x.com"]}, is_enabled=True),
        NotificationEndpoint(channel=NotificationChannel.SMS, config={"phone_number": "+48"}, is_enabled=True),
        NotificationEndpoint(channel=NotificationChannel.WEBHOOK, config={"url": "https://x.com"}, is_enabled=True),
    ]
    await NotificationEngine.send_alarm_notification(alarm, endpoints)


@pytest.mark.asyncio
async def test_no_duplicate_pending_alarm():
    factory, engine = await _fresh_session_factory()
    try:
        ae = AlarmEngine(factory)
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await _seed_sensor(session, obj, initial_temp=10.0, last_message_offset_s=5)
            await _seed_alarm_config(session, sensor, AlarmType.HIGH_TEMPERATURE, threshold=8.0)

        await ae._evaluate_all()
        await ae._evaluate_all()

        async with factory() as session:
            result = await session.execute(
                select(Alarm).where(Alarm.sensor_id == sensor.id, Alarm.alarm_type == AlarmType.HIGH_TEMPERATURE)
            )
            assert len(result.scalars().all()) == 1
    finally:
        await engine.dispose()


def test_build_description_high_temp():
    desc = _build_description(AlarmType.HIGH_TEMPERATURE, 8.5)
    assert "High temperature" in desc and "8.5" in desc


def test_build_description_low_temp():
    desc = _build_description(AlarmType.LOW_TEMPERATURE, -18.0)
    assert "Low temperature" in desc and "-18.0" in desc


def test_build_description_offline():
    desc = _build_description(AlarmType.OFFLINE, 120.0)
    assert "offline" in desc.lower() and "120" in desc