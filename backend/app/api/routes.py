"""FrigoCore — REST API endpoints for all domain entities.

OpenAPI documented, Pydantic-validated, async SQLAlchemy.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import AlarmStatus, AlarmType, NotificationChannel, UserRole
from app.models.alarm import Alarm
from app.models.alarm_config import AlarmConfig
from app.models.measurement import Measurement
from app.models.notification_endpoint import NotificationEndpoint
from app.models.notification_profile import NotificationProfile
from app.models.object import Object
from app.models.sensor import Sensor
from app.models.user import User
from app.schemas import (
    AlarmAcknowledge,
    AlarmConfigCreate,
    AlarmConfigResponse,
    AlarmConfigUpdate,
    AlarmResponse,
    MeasurementResponse,
    NotificationEndpointCreate,
    NotificationEndpointResponse,
    NotificationEndpointUpdate,
    NotificationProfileCreate,
    NotificationProfileResponse,
    NotificationProfileUpdate,
    ObjectCreate,
    ObjectResponse,
    ObjectUpdate,
    ObjectUserAssign,
    SensorCreate,
    SensorReorder,
    SensorResponse,
    SensorUpdate,
    UserResponse,
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

objects_router = APIRouter()
users_router = APIRouter()
sensors_router = APIRouter()
alarm_configs_router = APIRouter()
alarms_router = APIRouter()
measurements_router = APIRouter()
notifications_router = APIRouter()


# ===================================================================
# Objects
# ===================================================================

def _sensor_is_online(sensor: Sensor, now: datetime) -> bool:
    """A sensor is online while its last message is inside its own timeout."""
    if sensor.last_message_at is None:
        return False
    last = sensor.last_message_at
    if last.tzinfo is None:  # SQLite stores naive UTC
        last = last.replace(tzinfo=timezone.utc)
    return (now - last).total_seconds() <= sensor.offline_timeout_seconds


async def _with_sensor_rollups(
    db: AsyncSession, objects: list[Object]
) -> list[ObjectResponse]:
    """Attach sensor counts and live online counts to object rows.

    The administration list shows each object's status and sensor count
    without expanding it, so the counts come back with the list rather than
    costing one request per row.
    """
    responses = [ObjectResponse.model_validate(obj) for obj in objects]
    if not responses:
        return responses

    result = await db.execute(
        select(Sensor).where(Sensor.object_id.in_([obj.id for obj in objects]))
    )
    now = datetime.now(timezone.utc)
    by_object: dict[UUID, list[Sensor]] = {}
    for sensor in result.scalars().all():
        by_object.setdefault(sensor.object_id, []).append(sensor)

    for response in responses:
        sensors = by_object.get(response.id, [])
        response.sensor_count = len(sensors)
        response.online_sensor_count = sum(1 for s in sensors if _sensor_is_online(s, now))
    return responses


@objects_router.get("", response_model=list[ObjectResponse])
async def list_objects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ObjectResponse]:
    result = await db.execute(
        select(Object).offset(skip).limit(limit).order_by(Object.name)
    )
    return await _with_sensor_rollups(db, list(result.scalars().all()))


@objects_router.post("", response_model=ObjectResponse, status_code=status.HTTP_201_CREATED)
async def create_object(body: ObjectCreate, db: AsyncSession = Depends(get_db)) -> Object:
    obj = Object(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@objects_router.get("/{object_id}", response_model=ObjectResponse)
async def get_object(object_id: UUID, db: AsyncSession = Depends(get_db)) -> ObjectResponse:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return (await _with_sensor_rollups(db, [obj]))[0]


@objects_router.patch("/{object_id}", response_model=ObjectResponse)
async def update_object(
    object_id: UUID, body: ObjectUpdate, db: AsyncSession = Depends(get_db)
) -> Object:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@objects_router.delete("/{object_id}")
async def delete_object(object_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    await db.delete(obj)
    await db.commit()
    return {"status": "deleted"}


# ===================================================================
# Object access (users assigned to an object)
#
# This reuses the existing User.object_id relationship rather than adding a
# join table: the data model already says a Client belongs to exactly one
# Object, and an Admin (object_id NULL) already sees everything.
# ===================================================================

@objects_router.get("/{object_id}/users", response_model=list[UserResponse])
async def list_object_users(
    object_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[User]:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    result = await db.execute(
        select(User).where(User.object_id == object_id).order_by(User.username)
    )
    return result.scalars().all()


@objects_router.post("/{object_id}/users", response_model=UserResponse)
async def assign_user_to_object(
    object_id: UUID, body: ObjectUserAssign, db: AsyncSession = Depends(get_db)
) -> User:
    """Grant a user access to this object."""
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    user = await db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == UserRole.ADMIN:
        # Admins already see every object; pinning one would narrow, not widen,
        # their access and would misrepresent it in the access list.
        raise HTTPException(
            status_code=400,
            detail="Administrators already have access to every object",
        )
    user.object_id = object_id
    await db.commit()
    await db.refresh(user)
    return user


@objects_router.delete("/{object_id}/users/{user_id}", response_model=UserResponse)
async def revoke_user_from_object(
    object_id: UUID, user_id: UUID, db: AsyncSession = Depends(get_db)
) -> User:
    """Revoke a user's access to this object."""
    user = await db.get(User, user_id)
    if user is None or user.object_id != object_id:
        raise HTTPException(status_code=404, detail="User is not assigned to this object")
    user.object_id = None
    await db.commit()
    await db.refresh(user)
    return user


# ===================================================================
# Users (directory for object-access administration)
# ===================================================================

@users_router.get("", response_model=list[UserResponse])
async def list_users(
    unassigned_only: bool = Query(False, description="Only users with no object assigned"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    """List users so an administrator can pick one to assign to an object.

    Read-only, and UserResponse carries no credential fields — this endpoint
    exists to populate the access picker, not to manage accounts.
    """
    stmt = select(User)
    if unassigned_only:
        stmt = stmt.where(User.object_id.is_(None))
    stmt = stmt.order_by(User.username).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


# ===================================================================
# Sensors
# ===================================================================

@sensors_router.get("/{object_id}/sensors", response_model=list[SensorResponse])
async def list_sensors(
    object_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[Sensor]:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    result = await db.execute(
        select(Sensor)
        .where(Sensor.object_id == object_id)
        .offset(skip)
        .limit(limit)
        .order_by(Sensor.display_order, Sensor.name)
    )
    return result.scalars().all()


@sensors_router.post("/{object_id}/sensors", response_model=SensorResponse, status_code=status.HTTP_201_CREATED)
async def create_sensor(
    object_id: UUID, body: SensorCreate, db: AsyncSession = Depends(get_db)
) -> Sensor:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    # New sensors go to the end of the object's dashboard order rather than
    # silently tying for position 0 with everything else.
    highest = await db.scalar(
        select(func.max(Sensor.display_order)).where(Sensor.object_id == object_id)
    )
    sensor = Sensor(
        object_id=object_id,
        display_order=0 if highest is None else highest + 1,
        **body.model_dump(),
    )
    db.add(sensor)
    await db.commit()
    await db.refresh(sensor)
    return sensor


@sensors_router.post("/{object_id}/sensors/reorder", response_model=list[SensorResponse])
async def reorder_sensors(
    object_id: UUID, body: SensorReorder, db: AsyncSession = Depends(get_db)
) -> list[Sensor]:
    """Persist the dashboard display order for an object's sensors.

    Ordering belongs to the object's configuration, so it is stored once and
    every client viewing that object sees the same sequence.
    """
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")

    result = await db.execute(select(Sensor).where(Sensor.object_id == object_id))
    sensors = {sensor.id: sensor for sensor in result.scalars().all()}

    unknown = [str(sid) for sid in body.sensor_ids if sid not in sensors]
    if unknown:
        raise HTTPException(
            status_code=404,
            detail=f"Sensors do not belong to this object: {', '.join(unknown)}",
        )
    if len(set(body.sensor_ids)) != len(body.sensor_ids):
        raise HTTPException(status_code=400, detail="Duplicate sensor ids in ordering")

    for position, sensor_id in enumerate(body.sensor_ids):
        sensors[sensor_id].display_order = position
    # Sensors the client didn't list (e.g. one added by someone else since
    # the page loaded) keep a stable position after the ones it did.
    trailing = sorted(
        (s for s in sensors.values() if s.id not in set(body.sensor_ids)),
        key=lambda s: (s.display_order, s.name),
    )
    for offset, sensor in enumerate(trailing):
        sensor.display_order = len(body.sensor_ids) + offset

    await db.commit()
    result = await db.execute(
        select(Sensor)
        .where(Sensor.object_id == object_id)
        .order_by(Sensor.display_order, Sensor.name)
    )
    return result.scalars().all()


@sensors_router.get("/{object_id}/sensors/{sensor_id}", response_model=SensorResponse)
async def get_sensor(
    object_id: UUID, sensor_id: UUID, db: AsyncSession = Depends(get_db)
) -> Sensor:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None or sensor.object_id != object_id:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor


@sensors_router.patch("/{object_id}/sensors/{sensor_id}", response_model=SensorResponse)
async def update_sensor(
    object_id: UUID,
    sensor_id: UUID,
    body: SensorUpdate,
    db: AsyncSession = Depends(get_db),
) -> Sensor:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None or sensor.object_id != object_id:
        raise HTTPException(status_code=404, detail="Sensor not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(sensor, field, value)
    await db.commit()
    await db.refresh(sensor)
    return sensor


@sensors_router.delete("/{object_id}/sensors/{sensor_id}")
async def delete_sensor(
    object_id: UUID, sensor_id: UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None or sensor.object_id != object_id:
        raise HTTPException(status_code=404, detail="Sensor not found")
    await db.delete(sensor)
    await db.commit()
    return {"status": "deleted"}


# ===================================================================
# Alarm Configs (per sensor — legacy normalized)
# ===================================================================

@alarm_configs_router.get("/{sensor_id}/alarm-configs", response_model=list[AlarmConfigResponse])
async def list_alarm_configs(
    sensor_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[AlarmConfig]:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    result = await db.execute(
        select(AlarmConfig).where(AlarmConfig.sensor_id == sensor_id).order_by(AlarmConfig.alarm_type)
    )
    return result.scalars().all()


@alarm_configs_router.post("/{sensor_id}/alarm-configs", response_model=AlarmConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_alarm_config(
    sensor_id: UUID, body: AlarmConfigCreate, db: AsyncSession = Depends(get_db)
) -> AlarmConfig:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    # Prevent duplicate alarm types
    existing = await db.scalar(
        select(AlarmConfig).where(
            AlarmConfig.sensor_id == sensor_id,
            AlarmConfig.alarm_type == body.alarm_type,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"AlarmConfig type '{body.alarm_type}' already exists for this sensor")
    config = AlarmConfig(sensor_id=sensor_id, **body.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@alarm_configs_router.patch("/{sensor_id}/alarm-configs/{config_id}", response_model=AlarmConfigResponse)
async def update_alarm_config(
    sensor_id: UUID,
    config_id: UUID,
    body: AlarmConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> AlarmConfig:
    config = await db.get(AlarmConfig, config_id)
    if config is None or config.sensor_id != sensor_id:
        raise HTTPException(status_code=404, detail="AlarmConfig not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    await db.commit()
    await db.refresh(config)
    return config


@alarm_configs_router.delete("/{sensor_id}/alarm-configs/{config_id}")
async def delete_alarm_config(
    sensor_id: UUID, config_id: UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    config = await db.get(AlarmConfig, config_id)
    if config is None or config.sensor_id != sensor_id:
        raise HTTPException(status_code=404, detail="AlarmConfig not found")
    await db.delete(config)
    await db.commit()
    return {"status": "deleted"}


# ===================================================================
# Alarms
# ===================================================================

@alarms_router.get("", response_model=list[AlarmResponse])
async def list_alarms(
    object_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[Alarm]:
    stmt = select(Alarm)
    if object_id:
        stmt = stmt.where(Alarm.object_id == object_id)
    if status_filter:
        stmt = stmt.where(Alarm.status == status_filter)
    stmt = stmt.order_by(Alarm.detected_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@alarms_router.get("/{alarm_id}", response_model=AlarmResponse)
async def get_alarm(alarm_id: UUID, db: AsyncSession = Depends(get_db)) -> Alarm:
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return alarm


@alarms_router.post("/{alarm_id}/acknowledge", response_model=AlarmResponse)
async def acknowledge_alarm(
    alarm_id: UUID, _body: AlarmAcknowledge = ..., db: AsyncSession = Depends(get_db)
) -> Alarm:
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    if alarm.status != AlarmStatus.TRIGGERED:
        raise HTTPException(status_code=400, detail="Only TRIGGERED alarms can be acknowledged")
    alarm.status = AlarmStatus.ACKNOWLEDGED
    alarm.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(alarm)
    return alarm


@alarms_router.post("/{alarm_id}/archive", response_model=AlarmResponse)
async def archive_alarm(alarm_id: UUID, db: AsyncSession = Depends(get_db)) -> Alarm:
    """Hide a completed alarm without deleting its record or chart evidence."""
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    if alarm.status not in (AlarmStatus.ACKNOWLEDGED, AlarmStatus.RESOLVED):
        raise HTTPException(status_code=400, detail="Only completed alarms can be archived")
    alarm.status = AlarmStatus.ARCHIVED
    await db.commit()
    await db.refresh(alarm)
    return alarm


# ===================================================================
# Measurements
# ===================================================================

@measurements_router.get("/{sensor_id}/measurements", response_model=list[MeasurementResponse])
async def list_measurements(
    sensor_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[Measurement]:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    result = await db.execute(
        select(Measurement)
        .where(Measurement.sensor_id == sensor_id)
        .order_by(Measurement.received_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


# Hard ceiling on rows pulled from the DB for a single aggregation request,
# regardless of the requested time window. The API has no auth/firewall in
# front of it, so this is what stands between a `since` far in the past and
# an unbounded table scan — chosen generously above any realistic reporting
# rate over the widest supported range (7D) so real charts never get
# truncated by it.
MAX_AGGREGATION_ROWS = 100_000


def _decimate_measurements(rows: list[Measurement], target_points: int) -> list[Measurement]:
    """Reduce `rows` (ascending by received_at) to ~target_points by taking
    the min and max temperature per time bucket, preserving real excursions
    instead of averaging them away. Mirrors the chart's original
    client-side decimation, now run server-side so the frontend never has
    to fetch more than it will actually render."""
    if len(rows) <= target_points:
        return rows
    bucket_size = math.ceil(len(rows) / max(target_points / 2, 1))
    result: list[Measurement] = []
    for i in range(0, len(rows), bucket_size):
        bucket = rows[i : i + bucket_size]
        if not bucket:
            continue
        min_r = min(bucket, key=lambda r: r.temperature)
        max_r = max(bucket, key=lambda r: r.temperature)
        if min_r is max_r:
            result.append(min_r)
        elif min_r.received_at <= max_r.received_at:
            result.append(min_r)
            result.append(max_r)
        else:
            result.append(max_r)
            result.append(min_r)
    return result


@measurements_router.get("/{sensor_id}/measurements/aggregated", response_model=list[MeasurementResponse])
async def list_measurements_aggregated(
    sensor_id: UUID,
    since: datetime = Query(...),
    until: datetime | None = Query(None),
    target_points: int = Query(80, ge=10, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[Measurement]:
    """Chart data endpoint. Aggregates readings in [since, until] down to
    ~target_points columns instead of returning a fixed number of raw
    points — the frontend sizes target_points from its actual rendered
    chart width, so a phone and a desktop chart get comparable column
    density instead of one being sparse or the other overcrowded.
    """
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    until_dt = until or datetime.now(timezone.utc)
    result = await db.execute(
        select(Measurement)
        .where(
            Measurement.sensor_id == sensor_id,
            Measurement.received_at >= since,
            Measurement.received_at <= until_dt,
        )
        .order_by(Measurement.received_at.asc())
        .limit(MAX_AGGREGATION_ROWS)
    )
    rows = list(result.scalars().all())
    decimated = _decimate_measurements(rows, target_points)
    # The plain /measurements endpoint returns newest-first, and the
    # frontend's readings computed (DashboardView.vue) always .reverse()s
    # that into oldest-first before handing it to the chart. Match that
    # same newest-first contract here so the existing reverse() keeps
    # producing correctly-ordered, ascending data for the chart's xDomain —
    # returning ascending here instead silently double-reverses it.
    decimated.reverse()
    return decimated


# ===================================================================
# Notification Profiles
# ===================================================================

@notifications_router.get("/{object_id}/notification-profile", response_model=NotificationProfileResponse)
async def get_notification_profile(
    object_id: UUID, db: AsyncSession = Depends(get_db)
) -> NotificationProfile:
    profile = await db.scalar(
        select(NotificationProfile).where(NotificationProfile.object_id == object_id)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Notification profile not found")
    return profile


@notifications_router.post("/{object_id}/notification-profile", response_model=NotificationProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_profile(
    object_id: UUID, body: NotificationProfileCreate, db: AsyncSession = Depends(get_db)
) -> NotificationProfile:
    existing = await db.scalar(
        select(NotificationProfile).where(NotificationProfile.object_id == object_id)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Notification profile already exists for this object")
    profile = NotificationProfile(object_id=object_id, **body.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@notifications_router.patch("/{object_id}/notification-profile", response_model=NotificationProfileResponse)
async def update_notification_profile(
    object_id: UUID, body: NotificationProfileUpdate, db: AsyncSession = Depends(get_db)
) -> NotificationProfile:
    profile = await db.scalar(
        select(NotificationProfile).where(NotificationProfile.object_id == object_id)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Notification profile not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return profile


# ===================================================================
# Notification Endpoints (belong to a profile)
# ===================================================================

@notifications_router.get("/{object_id}/notification-endpoints", response_model=list[NotificationEndpointResponse])
async def list_notification_endpoints(
    object_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[NotificationEndpoint]:
    profile = await db.scalar(
        select(NotificationProfile).where(NotificationProfile.object_id == object_id)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Notification profile not found")
    result = await db.execute(
        select(NotificationEndpoint)
        .where(NotificationEndpoint.profile_id == profile.id)
        .order_by(NotificationEndpoint.channel, NotificationEndpoint.label)
    )
    return result.scalars().all()


@notifications_router.post("/{object_id}/notification-endpoints", response_model=NotificationEndpointResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_endpoint(
    object_id: UUID,
    body: NotificationEndpointCreate,
    db: AsyncSession = Depends(get_db),
) -> NotificationEndpoint:
    profile = await db.scalar(
        select(NotificationProfile).where(NotificationProfile.object_id == object_id)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Notification profile not found — create one first")
    endpoint = NotificationEndpoint(profile_id=profile.id, **body.model_dump())
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return endpoint


@notifications_router.patch(
    "/{object_id}/notification-endpoints/{endpoint_id}",
    response_model=NotificationEndpointResponse,
)
async def update_notification_endpoint(
    object_id: UUID,
    endpoint_id: UUID,
    body: NotificationEndpointUpdate,
    db: AsyncSession = Depends(get_db),
) -> NotificationEndpoint:
    endpoint = await db.get(NotificationEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Notification endpoint not found")
    # Verify endpoint belongs to the correct profile
    profile = await db.scalar(
        select(NotificationProfile).where(NotificationProfile.object_id == object_id)
    )
    if profile is None or endpoint.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Notification endpoint not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(endpoint, field, value)
    await db.commit()
    await db.refresh(endpoint)
    return endpoint


@notifications_router.delete("/{object_id}/notification-endpoints/{endpoint_id}")
async def delete_notification_endpoint(
    object_id: UUID, endpoint_id: UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    endpoint = await db.get(NotificationEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Notification endpoint not found")
    profile = await db.scalar(
        select(NotificationProfile).where(NotificationProfile.object_id == object_id)
    )
    if profile is None or endpoint.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Notification endpoint not found")
    await db.delete(endpoint)
    await db.commit()
    return {"status": "deleted"}
