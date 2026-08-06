"""FrigoCore — REST API endpoints for all domain entities.

OpenAPI documented, Pydantic-validated, async SQLAlchemy.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import AlarmStatus, AlarmType, NotificationChannel
from app.models.alarm import Alarm
from app.models.alarm_config import AlarmConfig
from app.models.measurement import Measurement
from app.models.notification_endpoint import NotificationEndpoint
from app.models.notification_profile import NotificationProfile
from app.models.object import Object
from app.models.sensor import Sensor
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
    ObjectCreate,
    ObjectResponse,
    ObjectUpdate,
    SensorCreate,
    SensorResponse,
    SensorUpdate,
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

objects_router = APIRouter()
sensors_router = APIRouter()
alarm_configs_router = APIRouter()
alarms_router = APIRouter()
measurements_router = APIRouter()
notifications_router = APIRouter()


# ===================================================================
# Objects
# ===================================================================

@objects_router.get("", response_model=list[ObjectResponse])
async def list_objects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[Object]:
    result = await db.execute(
        select(Object).offset(skip).limit(limit).order_by(Object.name)
    )
    return result.scalars().all()


@objects_router.post("", response_model=ObjectResponse, status_code=status.HTTP_201_CREATED)
async def create_object(body: ObjectCreate, db: AsyncSession = Depends(get_db)) -> Object:
    obj = Object(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@objects_router.get("/{object_id}", response_model=ObjectResponse)
async def get_object(object_id: UUID, db: AsyncSession = Depends(get_db)) -> Object:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj


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
        .order_by(Sensor.name)
    )
    return result.scalars().all()


@sensors_router.post("/{object_id}/sensors", response_model=SensorResponse, status_code=status.HTTP_201_CREATED)
async def create_sensor(
    object_id: UUID, body: SensorCreate, db: AsyncSession = Depends(get_db)
) -> Sensor:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    sensor = Sensor(object_id=object_id, **body.model_dump())
    db.add(sensor)
    await db.commit()
    await db.refresh(sensor)
    return sensor


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