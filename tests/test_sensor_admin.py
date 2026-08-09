"""Tests for the administrator sensor/object configuration API.

Covers what the Objects administration panel persists: sensor icon,
calibration offset, dashboard display order, and which users have access to
an object.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes import (
    assign_user_to_object,
    create_sensor,
    list_object_users,
    list_sensors,
    list_users,
    reorder_sensors,
    revoke_user_from_object,
    update_sensor,
)
from app.enums import UserRole
from app.models.base import Base
from app.models.object import Object
from app.models.sensor import Sensor
from app.models.user import User
from app.mqtt.client import MQTTEngine
from app.schemas import ObjectUserAssign, SensorCreate, SensorReorder, SensorUpdate

from fastapi import HTTPException


async def _fresh_session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False), engine


async def _seed_object(session: AsyncSession, name: str = "Kotlety z Biskupca") -> Object:
    obj = Object(name=name)
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def _seed_user(session: AsyncSession, username: str, role: UserRole = UserRole.CLIENT) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="not-a-real-hash",
        full_name=username.title(),
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Sensor defaults, icon and calibration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sensor_defaults() -> None:
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await create_sensor(
                obj.id,
                SensorCreate(name="Agregat 1", mqtt_topic="frigo/kb/agregat-1"),
                db=session,
            )
            assert sensor.icon == "thermometer"
            assert sensor.calibration_offset == 0.0
            assert sensor.display_order == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_icon_and_calibration_persist() -> None:
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await create_sensor(
                obj.id,
                SensorCreate(
                    name="Parownik", mqtt_topic="frigo/kb/parownik",
                    icon="evaporator", calibration_offset=-0.5,
                ),
                db=session,
            )
            await update_sensor(
                obj.id, sensor.id,
                SensorUpdate(icon="condenser", calibration_offset=1.25),
                db=session,
            )

        # Re-read through a fresh session — this is what a page reload does.
        async with factory() as session:
            reloaded = await session.get(Sensor, sensor.id)
            assert reloaded.icon == "condenser"
            assert reloaded.calibration_offset == 1.25
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_icon_identifier_is_validated() -> None:
    """Icons are stored as slugs; anything else must be rejected up front."""
    with pytest.raises(ValueError):
        SensorUpdate(icon="<script>alert(1)</script>")
    with pytest.raises(ValueError):
        SensorUpdate(icon="Snowflake Icon")


@pytest.mark.asyncio
async def test_calibration_offset_is_bounded() -> None:
    with pytest.raises(ValueError):
        SensorUpdate(calibration_offset=500.0)


@pytest.mark.asyncio
async def test_calibration_offset_applied_at_ingest() -> None:
    """A configured offset must reach the stored reading, not just the form.

    The alarm engine compares thresholds against Sensor.current_temperature,
    so calibration has to be applied on the way in or it would mean nothing.
    """
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            sensor = await create_sensor(
                obj.id,
                SensorCreate(
                    name="Komora", mqtt_topic="frigo/kb/komora",
                    calibration_offset=-0.5,
                ),
                db=session,
            )

        async with factory() as session:
            await MQTTEngine._persist_measurement(session, "frigo/kb/komora", 4.0)
            await session.commit()

        async with factory() as session:
            reloaded = await session.get(Sensor, sensor.id)
            assert reloaded.current_temperature == 3.5
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Display order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_sensors_append_to_the_end_of_the_order() -> None:
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            orders = []
            for i in range(3):
                sensor = await create_sensor(
                    obj.id,
                    SensorCreate(name=f"S{i}", mqtt_topic=f"frigo/kb/s{i}"),
                    db=session,
                )
                orders.append(sensor.display_order)
            assert orders == [0, 1, 2]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reorder_persists_and_drives_listing() -> None:
    """Ordering is object configuration, so it must survive the request.

    Every client reading the object gets the same sequence back — this is
    what makes it a shared setting rather than per-user state.
    """
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            created = [
                await create_sensor(
                    obj.id, SensorCreate(name=n, mqtt_topic=f"frigo/kb/{n}"), db=session
                )
                for n in ("alpha", "bravo", "charlie")
            ]
            reversed_ids = [s.id for s in reversed(created)]
            await reorder_sensors(obj.id, SensorReorder(sensor_ids=reversed_ids), db=session)

        async with factory() as session:
            listed = await list_sensors(obj.id, skip=0, limit=100, db=session)
            assert [s.name for s in listed] == ["charlie", "bravo", "alpha"]
            assert [s.display_order for s in listed] == [0, 1, 2]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reorder_rejects_foreign_sensor() -> None:
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj_a = await _seed_object(session, "A")
            obj_b = await _seed_object(session, "B")
            own = await create_sensor(
                obj_a.id, SensorCreate(name="own", mqtt_topic="frigo/a/own"), db=session
            )
            foreign = await create_sensor(
                obj_b.id, SensorCreate(name="foreign", mqtt_topic="frigo/b/foreign"), db=session
            )
            with pytest.raises(HTTPException) as exc:
                await reorder_sensors(
                    obj_a.id, SensorReorder(sensor_ids=[own.id, foreign.id]), db=session
                )
            assert exc.value.status_code == 404
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reorder_keeps_unlisted_sensors_after_the_listed_ones() -> None:
    """A sensor added since the page loaded must not vanish or collide."""
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            a = await create_sensor(obj.id, SensorCreate(name="a", mqtt_topic="t/a"), db=session)
            b = await create_sensor(obj.id, SensorCreate(name="b", mqtt_topic="t/b"), db=session)
            late = await create_sensor(obj.id, SensorCreate(name="late", mqtt_topic="t/late"), db=session)

            await reorder_sensors(obj.id, SensorReorder(sensor_ids=[b.id, a.id]), db=session)

        async with factory() as session:
            listed = await list_sensors(obj.id, skip=0, limit=100, db=session)
            assert [s.name for s in listed] == ["b", "a", "late"]
            assert len({s.display_order for s in listed}) == 3
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Object list rollups
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_object_list_reports_sensor_and_online_counts() -> None:
    """The admin list renders status per object without expanding it."""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from app.api.routes import list_objects  # noqa: PLC0415

    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            now = datetime.now(timezone.utc)
            fresh = await create_sensor(
                obj.id, SensorCreate(name="fresh", mqtt_topic="t/fresh"), db=session
            )
            stale = await create_sensor(
                obj.id, SensorCreate(name="stale", mqtt_topic="t/stale"), db=session
            )
            never = await create_sensor(
                obj.id, SensorCreate(name="never", mqtt_topic="t/never"), db=session
            )
            fresh.last_message_at = now - timedelta(seconds=10)
            stale.last_message_at = now - timedelta(seconds=10_000)
            assert never.last_message_at is None
            await session.commit()

        async with factory() as session:
            rows = await list_objects(skip=0, limit=100, db=session)
            assert rows[0].sensor_count == 3
            assert rows[0].online_sensor_count == 1
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Object access
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assign_and_revoke_object_access() -> None:
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            user = await _seed_user(session, "anna")

            await assign_user_to_object(obj.id, ObjectUserAssign(user_id=user.id), db=session)

        async with factory() as session:
            assigned = await list_object_users(obj.id, db=session)
            assert [u.username for u in assigned] == ["anna"]

        async with factory() as session:
            await revoke_user_from_object(obj.id, user.id, db=session)

        async with factory() as session:
            assert await list_object_users(obj.id, db=session) == []
            reloaded = await session.get(User, user.id)
            assert reloaded.object_id is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_revoking_a_user_of_another_object_is_rejected() -> None:
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj_a = await _seed_object(session, "A")
            obj_b = await _seed_object(session, "B")
            user = await _seed_user(session, "bogdan")
            await assign_user_to_object(obj_a.id, ObjectUserAssign(user_id=user.id), db=session)

            with pytest.raises(HTTPException) as exc:
                await revoke_user_from_object(obj_b.id, user.id, db=session)
            assert exc.value.status_code == 404

            refreshed = await session.get(User, user.id)
            assert refreshed.object_id == obj_a.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admins_are_not_pinned_to_a_single_object() -> None:
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            admin = await _seed_user(session, "root", role=UserRole.ADMIN)
            with pytest.raises(HTTPException) as exc:
                await assign_user_to_object(obj.id, ObjectUserAssign(user_id=admin.id), db=session)
            assert exc.value.status_code == 400
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_directory_never_exposes_password_hashes() -> None:
    """The access picker is read-only and must not leak credentials."""
    from app.schemas import UserResponse  # noqa: PLC0415

    assert "hashed_password" not in UserResponse.model_fields

    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            await _seed_user(session, "clara")
            users = await list_users(unassigned_only=False, skip=0, limit=100, db=session)
            payload = UserResponse.model_validate(users[0]).model_dump()
            assert "hashed_password" not in payload
            assert payload["username"] == "clara"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_directory_can_filter_to_unassigned() -> None:
    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            assigned = await _seed_user(session, "dana")
            await _seed_user(session, "erik")
            await assign_user_to_object(obj.id, ObjectUserAssign(user_id=assigned.id), db=session)

        async with factory() as session:
            free = await list_users(unassigned_only=True, skip=0, limit=100, db=session)
            assert [u.username for u in free] == ["erik"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleting_an_object_does_not_delete_its_users() -> None:
    """Object deletion must clear access, not remove people from the system."""
    from app.api.routes import delete_object  # noqa: PLC0415

    factory, engine = await _fresh_session_factory()
    try:
        async with factory() as session:
            obj = await _seed_object(session)
            user = await _seed_user(session, "fiona")
            await assign_user_to_object(obj.id, ObjectUserAssign(user_id=user.id), db=session)
            await delete_object(obj.id, db=session)

        async with factory() as session:
            remaining = (await session.execute(select(User))).scalars().all()
            assert [u.username for u in remaining] == ["fiona"]
            assert remaining[0].object_id is None
    finally:
        await engine.dispose()
