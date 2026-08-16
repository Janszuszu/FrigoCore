"""Existing alarm behavior must remain intact, and the migration must apply
cleanly against the test database (item 16 & 17 of the spec)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select

from app.database import async_session_factory, engine as db_engine
from app.enums import AlarmStatus, AlarmType, UserRole
from app.models.alarm import Alarm
from app.models.alarm_config import AlarmConfig
from app.models.sensor import Sensor
from app.services.alarm_engine import AlarmEngine

from .conftest import auth_headers
from .helpers import make_object


@pytest.mark.asyncio
async def test_migration_created_new_tables():
    """Sanity check that Alembic actually built the new schema — not just
    that Base.metadata knows about the models in memory."""

    def _table_names(sync_conn):
        return set(inspect(sync_conn).get_table_names())

    async with db_engine.connect() as conn:
        names = await conn.run_sync(_table_names)

    for table in ("alarm_assignments", "alarm_events", "escalation_policies", "escalation_tiers", "device_tokens"):
        assert table in names


@pytest.mark.asyncio
async def test_alarm_engine_threshold_lifecycle_unaffected(db_session):
    """PENDING -> TRIGGERED -> RESOLVED via real sensor threshold evaluation,
    exactly as it worked before this feature — the dispatch layer must not
    have touched this path's own state transitions."""
    obj = await make_object(db_session, "Threshold Test Object")
    sensor = Sensor(
        name="Sensor A", mqtt_topic="test/sensor-a", object_id=obj.id,
        current_temperature=10.0, last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(sensor)
    await db_session.flush()
    config = AlarmConfig(
        alarm_type=AlarmType.HIGH_TEMPERATURE, threshold_value=5.0, trigger_delay_seconds=0,
        is_enabled=True, sensor_id=sensor.id,
    )
    db_session.add(config)
    await db_session.commit()

    alarm_engine = AlarmEngine(async_session_factory)
    await alarm_engine._evaluate_all()
    await alarm_engine._evaluate_all()  # second pass clears the PENDING delay (0s)

    async with async_session_factory() as session:
        alarm = await session.scalar(select(Alarm).where(Alarm.sensor_id == sensor.id))
    assert alarm is not None
    assert alarm.status == AlarmStatus.TRIGGERED

    # Condition clears -> auto-resolve, same as before this feature existed.
    async with async_session_factory() as session:
        s = await session.get(Sensor, sensor.id)
        s.current_temperature = 2.0
        await session.commit()

    await alarm_engine._evaluate_all()

    async with async_session_factory() as session:
        alarm = await session.scalar(select(Alarm).where(Alarm.sensor_id == sensor.id))
    assert alarm.status == AlarmStatus.RESOLVED


@pytest.mark.asyncio
async def test_legacy_acknowledge_and_archive_still_work(client, db_session, make_user):
    """No escalation policy configured at all — the original dashboard flow
    (acknowledge then archive, no technician assignment involved) must keep
    working exactly as it did before."""
    from .helpers import make_triggered_alarm

    serwisant = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    alarm = await make_triggered_alarm(db_session, obj.id)

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/acknowledge", headers=auth_headers(serwisant))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == AlarmStatus.ACKNOWLEDGED.value

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/archive", headers=auth_headers(serwisant))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == AlarmStatus.ARCHIVED.value
