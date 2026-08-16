"""FrigoCore — REST API endpoints for all domain entities.

OpenAPI documented, Pydantic-validated, async SQLAlchemy.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_visible_object_ids, require_admin
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.enums import (
    AlarmEventType,
    AlarmStatus,
    AlarmType,
    AssignmentOutcome,
    EscalationTargetType,
    NotificationChannel,
    UserRole,
)
from app.models.alarm import Alarm
from app.models.alarm_assignment import AlarmAssignment
from app.models.alarm_config import AlarmConfig
from app.models.alarm_event import AlarmEvent
from app.models.device_token import DeviceToken
from app.models.escalation_policy import EscalationPolicy, EscalationTier
from app.models.measurement import Measurement
from app.models.notification_endpoint import NotificationEndpoint
from app.models.notification_profile import NotificationProfile
from app.models.object import Object
from app.models.sensor import Sensor
from app.models.user import User
from app.schemas import (
    AlarmAssignmentResponse,
    AlarmConfigCreate,
    AlarmConfigResponse,
    AlarmConfigUpdate,
    AlarmEventResponse,
    AlarmResponse,
    DeviceTokenRegister,
    DeviceTokenResponse,
    EscalationPolicyCreate,
    EscalationPolicyResponse,
    EscalationTierCreate,
    EscalationTierResponse,
    LoginRequest,
    LoginResponse,
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
    UserCreate,
    UserPasswordSet,
    UserResponse,
    UserUpdate,
)
from app.services.dispatch_service import escalate, record_event
from app.services.notification_engine import NotificationEngine

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

auth_router = APIRouter()
objects_router = APIRouter()
users_router = APIRouter()
sensors_router = APIRouter()
alarm_configs_router = APIRouter()
alarms_router = APIRouter()
measurements_router = APIRouter()
notifications_router = APIRouter()
devices_router = APIRouter()
escalation_policies_router = APIRouter()


def _check_object_visible(object_id: UUID, user: User) -> None:
    """404 (not 403) if `object_id` is outside the caller's visible set —
    a `user`-role account should not learn an object exists at all."""
    visible = get_visible_object_ids(user)
    if visible is not None and object_id not in visible:
        raise HTTPException(status_code=404, detail="Object not found")


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        object_ids=[obj.id for obj in user.objects],
    )


# ===================================================================
# Auth
# ===================================================================

@auth_router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    user = await db.scalar(
        select(User).where(User.username == body.username).options(selectinload(User.objects))
    )
    if user is None or not user.is_active or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowa nazwa użytkownika lub hasło")
    token = create_access_token(user)
    return LoginResponse(access_token=token, user=_user_response(user))


@auth_router.get("/me", response_model=UserResponse)
async def read_me(user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(user)


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
    user: User = Depends(get_current_user),
) -> list[ObjectResponse]:
    stmt = select(Object)
    visible = get_visible_object_ids(user)
    if visible is not None:
        stmt = stmt.where(Object.id.in_(visible))
    stmt = stmt.offset(skip).limit(limit).order_by(Object.name)
    result = await db.execute(stmt)
    return await _with_sensor_rollups(db, list(result.scalars().all()))


@objects_router.post("", response_model=ObjectResponse, status_code=status.HTTP_201_CREATED)
async def create_object(
    body: ObjectCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> Object:
    obj = Object(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@objects_router.get("/{object_id}", response_model=ObjectResponse)
async def get_object(
    object_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> ObjectResponse:
    _check_object_visible(object_id, user)
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return (await _with_sensor_rollups(db, [obj]))[0]


@objects_router.patch("/{object_id}", response_model=ObjectResponse)
async def update_object(
    object_id: UUID, body: ObjectUpdate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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
async def delete_object(
    object_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> dict:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    await db.delete(obj)
    await db.commit()
    return {"status": "deleted"}


# ===================================================================
# Object access (users assigned to an object) — admin only, backed by the
# user_objects join table.
# ===================================================================

@objects_router.get("/{object_id}/users", response_model=list[UserResponse])
async def list_object_users(
    object_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> list[UserResponse]:
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    result = await db.execute(
        select(User)
        .join(User.objects)
        .where(Object.id == object_id)
        .options(selectinload(User.objects))
        .order_by(User.username)
    )
    return [_user_response(u) for u in result.scalars().all()]


@objects_router.post("/{object_id}/users", response_model=UserResponse)
async def assign_user_to_object(
    object_id: UUID, body: ObjectUserAssign, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> UserResponse:
    """Grant a `user`-role account access to this object."""
    obj = await db.get(Object, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    user = await db.get(User, body.user_id, options=[selectinload(User.objects)])
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != UserRole.USER:
        # Admin and serwisant already see every object; pinning one would
        # misrepresent their access in the assignment list.
        raise HTTPException(
            status_code=400,
            detail="Only 'użytkownik' accounts are assigned to individual objects",
        )
    if obj not in user.objects:
        user.objects.append(obj)
        await db.commit()
        await db.refresh(user, attribute_names=["objects"])
    return _user_response(user)


@objects_router.delete("/{object_id}/users/{user_id}", response_model=UserResponse)
async def revoke_user_from_object(
    object_id: UUID, user_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> UserResponse:
    """Revoke a user's access to this object."""
    user = await db.get(User, user_id, options=[selectinload(User.objects)])
    obj = await db.get(Object, object_id)
    if user is None or obj is None or obj not in user.objects:
        raise HTTPException(status_code=404, detail="User is not assigned to this object")
    user.objects.remove(obj)
    await db.commit()
    await db.refresh(user, attribute_names=["objects"])
    return _user_response(user)


# ===================================================================
# Users (account administration) — admin only
# ===================================================================

@users_router.get("", response_model=list[UserResponse])
async def list_users(
    unassigned_only: bool = Query(False, description="Only 'użytkownik' accounts with no object assigned"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[UserResponse]:
    stmt = select(User).options(selectinload(User.objects))
    if unassigned_only:
        stmt = stmt.where(~User.objects.any())
    stmt = stmt.order_by(User.username).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return [_user_response(u) for u in result.scalars().all()]


@users_router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> UserResponse:
    existing = await db.scalar(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if existing:
        raise HTTPException(status_code=409, detail="Nazwa użytkownika lub e-mail już istnieje")
    object_ids = body.object_ids if body.role == UserRole.USER else []
    objects: list[Object] = []
    if object_ids:
        result = await db.execute(select(Object).where(Object.id.in_(object_ids)))
        objects = list(result.scalars().all())
        if len(objects) != len(set(object_ids)):
            raise HTTPException(status_code=404, detail="One or more objects not found")
    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
        objects=objects,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user, attribute_names=["objects"])
    return _user_response(user)


@users_router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID, body: UserUpdate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> UserResponse:
    user = await db.get(User, user_id, options=[selectinload(User.objects)])
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    data = body.model_dump(exclude_unset=True)
    object_ids = data.pop("object_ids", None)
    for field, value in data.items():
        setattr(user, field, value)
    new_role = data.get("role", user.role)
    if object_ids is not None:
        if new_role != UserRole.USER and object_ids:
            raise HTTPException(status_code=400, detail="Tylko konta z rolą 'użytkownik' mają przypisane obiekty")
        result = await db.execute(select(Object).where(Object.id.in_(object_ids)))
        objects = list(result.scalars().all())
        if len(objects) != len(set(object_ids)):
            raise HTTPException(status_code=404, detail="One or more objects not found")
        user.objects = objects
    elif new_role != UserRole.USER and user.objects:
        # Role changed away from 'user' — an admin/serwisant seeing "everything"
        # shouldn't still carry a stale per-object assignment list.
        user.objects = []
    await db.commit()
    await db.refresh(user, attribute_names=["objects"])
    return _user_response(user)


@users_router.post("/{user_id}/password", response_model=UserResponse)
async def set_user_password(
    user_id: UUID, body: UserPasswordSet, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> UserResponse:
    user = await db.get(User, user_id, options=[selectinload(User.objects)])
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = hash_password(body.password)
    await db.commit()
    await db.refresh(user, attribute_names=["objects"])
    return _user_response(user)


@users_router.delete("/{user_id}")
async def delete_user(
    user_id: UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)
) -> dict:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Nie możesz usunąć własnego konta")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
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
    user: User = Depends(get_current_user),
) -> list[Sensor]:
    _check_object_visible(object_id, user)
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
    object_id: UUID, body: SensorCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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
    object_id: UUID, body: SensorReorder, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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
    object_id: UUID, sensor_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> Sensor:
    _check_object_visible(object_id, user)
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
    _admin: User = Depends(require_admin),
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
    object_id: UUID, sensor_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> dict:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None or sensor.object_id != object_id:
        raise HTTPException(status_code=404, detail="Sensor not found")
    await db.delete(sensor)
    await db.commit()
    return {"status": "deleted"}


# ===================================================================
# Alarm Configs (per sensor — legacy normalized). Configuration is an
# admin-only concern; serwisant/user accounts never edit or need to browse it.
# ===================================================================

@alarm_configs_router.get("/{sensor_id}/alarm-configs", response_model=list[AlarmConfigResponse])
async def list_alarm_configs(
    sensor_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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
    sensor_id: UUID, body: AlarmConfigCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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
    _admin: User = Depends(require_admin),
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
    sensor_id: UUID, config_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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
    user: User = Depends(get_current_user),
) -> list[Alarm]:
    if object_id is not None:
        _check_object_visible(object_id, user)
    stmt = select(Alarm)
    if object_id:
        stmt = stmt.where(Alarm.object_id == object_id)
    else:
        visible = get_visible_object_ids(user)
        if visible is not None:
            stmt = stmt.where(Alarm.object_id.in_(visible))
    if status_filter:
        stmt = stmt.where(Alarm.status == status_filter)
    stmt = stmt.order_by(Alarm.detected_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@alarms_router.get("/{alarm_id}", response_model=AlarmResponse)
async def get_alarm(
    alarm_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> Alarm:
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_object_visible(alarm.object_id, user)
    return alarm


async def _current_pending_assignment(db: AsyncSession, alarm_id: UUID) -> AlarmAssignment | None:
    return await db.scalar(
        select(AlarmAssignment).where(
            AlarmAssignment.alarm_id == alarm_id, AlarmAssignment.outcome == AssignmentOutcome.PENDING
        )
    )


async def _latest_accepted_assignment(db: AsyncSession, alarm_id: UUID) -> AlarmAssignment | None:
    return await db.scalar(
        select(AlarmAssignment)
        .where(AlarmAssignment.alarm_id == alarm_id, AlarmAssignment.outcome == AssignmentOutcome.ACCEPTED)
        .order_by(AlarmAssignment.responded_at.desc())
    )


def _user_matches_assignment(user: User, assignment: AlarmAssignment) -> bool:
    if assignment.target_user_id is not None:
        return assignment.target_user_id == user.id
    return assignment.target_role == user.role


@alarms_router.post("/{alarm_id}/accept", response_model=AlarmResponse)
async def accept_alarm(
    alarm_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> Alarm:
    """Current assigned technician accepts responsibility -> ACKNOWLEDGED.

    Race-safe: the assignment outcome flip is a single atomic UPDATE guarded
    by `outcome = 'pending'`. If two technicians (e.g. a role-tier assignment
    both are eligible for) hit this at the same time, exactly one UPDATE
    affects a row; the loser gets 409.
    """
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_object_visible(alarm.object_id, user)
    if alarm.status != AlarmStatus.TRIGGERED:
        raise HTTPException(status_code=400, detail="Only TRIGGERED alarms can be accepted")

    assignment = await _current_pending_assignment(db, alarm_id)
    if assignment is None:
        raise HTTPException(status_code=409, detail="No active assignment for this alarm")
    if not _user_matches_assignment(user, assignment):
        raise HTTPException(status_code=403, detail="This alarm is not currently assigned to you")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(AlarmAssignment)
        .where(AlarmAssignment.id == assignment.id, AlarmAssignment.outcome == AssignmentOutcome.PENDING)
        .values(outcome=AssignmentOutcome.ACCEPTED, responded_at=now, target_user_id=user.id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="This assignment was already resolved by someone else")

    alarm.status = AlarmStatus.ACKNOWLEDGED
    alarm.acknowledged_at = now
    await record_event(
        db, alarm.id, AlarmEventType.ASSIGNMENT_ACCEPTED, actor_user_id=user.id,
        metadata={"assignment_id": str(assignment.id), "tier": assignment.tier},
    )
    await record_event(db, alarm.id, AlarmEventType.ALARM_ACKNOWLEDGED, actor_user_id=user.id)
    await db.commit()
    await db.refresh(alarm)
    return alarm


@alarms_router.post("/{alarm_id}/decline", response_model=AlarmResponse)
async def decline_alarm(
    alarm_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> Alarm:
    """Current assigned technician declines -> assignment DECLINED, alarm stays
    TRIGGERED, escalation proceeds immediately (no waiting for the timeout)."""
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_object_visible(alarm.object_id, user)
    if alarm.status != AlarmStatus.TRIGGERED:
        raise HTTPException(status_code=400, detail="Only TRIGGERED alarms can be declined")

    assignment = await _current_pending_assignment(db, alarm_id)
    if assignment is None:
        raise HTTPException(status_code=409, detail="No active assignment for this alarm")
    if not _user_matches_assignment(user, assignment):
        raise HTTPException(status_code=403, detail="This alarm is not currently assigned to you")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(AlarmAssignment)
        .where(AlarmAssignment.id == assignment.id, AlarmAssignment.outcome == AssignmentOutcome.PENDING)
        .values(outcome=AssignmentOutcome.DECLINED, responded_at=now)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="This assignment was already resolved by someone else")

    await record_event(
        db, alarm.id, AlarmEventType.ASSIGNMENT_DECLINED, actor_user_id=user.id,
        metadata={"assignment_id": str(assignment.id), "tier": assignment.tier},
    )
    try:
        await escalate(db, alarm, previous_tier_order=assignment.tier, reason="declined")
    except IntegrityError:
        # Escalation engine's background cycle won the race and already
        # dispatched the next tier — the decline itself still succeeded.
        await db.rollback()
        raise HTTPException(status_code=409, detail="Escalation already in progress") from None
    await db.commit()
    await db.refresh(alarm)
    return alarm


@alarms_router.post("/{alarm_id}/en-route", response_model=AlarmResponse)
async def alarm_en_route(
    alarm_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> Alarm:
    """Current acknowledged technician confirms they are travelling to the
    site -> EN_ROUTE. This is the ONLY transition that triggers the
    client-facing "service is on the way" notification."""
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_object_visible(alarm.object_id, user)
    if alarm.status != AlarmStatus.ACKNOWLEDGED:
        raise HTTPException(status_code=400, detail="Only ACKNOWLEDGED alarms can go EN_ROUTE")

    accepted = await _latest_accepted_assignment(db, alarm_id)
    if accepted is None or (accepted.target_user_id != user.id and user.role != UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Only the accepting technician can mark EN_ROUTE")

    now = datetime.now(timezone.utc)
    alarm.status = AlarmStatus.EN_ROUTE
    alarm.en_route_at = now
    await record_event(db, alarm.id, AlarmEventType.ALARM_EN_ROUTE, actor_user_id=user.id)

    obj = await db.get(Object, alarm.object_id)
    await db.refresh(obj, attribute_names=["notification_profile"])
    endpoints: list[NotificationEndpoint] = []
    if obj.notification_profile is not None:
        await db.refresh(obj.notification_profile, attribute_names=["endpoints"])
        endpoints = obj.notification_profile.endpoints
    try:
        await NotificationEngine.send_service_on_the_way(alarm, endpoints)
    except Exception:
        pass  # Notification failure must not block the state transition
    await record_event(db, alarm.id, AlarmEventType.CLIENT_NOTIFIED, message="Service is on the way")

    await db.commit()
    await db.refresh(alarm)
    return alarm


@alarms_router.post("/{alarm_id}/resolve", response_model=AlarmResponse)
async def resolve_alarm(
    alarm_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> Alarm:
    """Technician marks the service issue resolved -> RESOLVED."""
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_object_visible(alarm.object_id, user)
    if alarm.status not in (AlarmStatus.ACKNOWLEDGED, AlarmStatus.EN_ROUTE):
        raise HTTPException(status_code=400, detail="Only ACKNOWLEDGED or EN_ROUTE alarms can be resolved")

    accepted = await _latest_accepted_assignment(db, alarm_id)
    if accepted is not None and accepted.target_user_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only the assigned technician can resolve this alarm")

    now = datetime.now(timezone.utc)
    alarm.status = AlarmStatus.RESOLVED
    alarm.resolved_at = now
    await record_event(db, alarm.id, AlarmEventType.ALARM_RESOLVED, actor_user_id=user.id)
    await db.commit()
    await db.refresh(alarm)
    return alarm


@alarms_router.get("/{alarm_id}/events", response_model=list[AlarmEventResponse])
async def list_alarm_events(
    alarm_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[AlarmEvent]:
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_object_visible(alarm.object_id, user)
    result = await db.execute(
        select(AlarmEvent).where(AlarmEvent.alarm_id == alarm_id).order_by(AlarmEvent.created_at)
    )
    return result.scalars().all()


@alarms_router.get("/{alarm_id}/assignments", response_model=list[AlarmAssignmentResponse])
async def list_alarm_assignments(
    alarm_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[AlarmAssignment]:
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_object_visible(alarm.object_id, user)
    result = await db.execute(
        select(AlarmAssignment).where(AlarmAssignment.alarm_id == alarm_id).order_by(AlarmAssignment.dispatched_at)
    )
    return result.scalars().all()


@alarms_router.post("/{alarm_id}/acknowledge", response_model=AlarmResponse)
async def acknowledge_alarm(
    alarm_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Alarm:
    """Legacy dashboard acknowledge — kept working for the existing web
    frontend, which acknowledges alarms directly without going through the
    technician-dispatch/assignment flow. When a pending assignment for this
    same user happens to exist, it is resolved as accepted too so the audit
    trail and assignment state stay consistent with the new /accept flow;
    otherwise this behaves exactly as it always has.
    """
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_object_visible(alarm.object_id, user)
    if alarm.status != AlarmStatus.TRIGGERED:
        raise HTTPException(status_code=400, detail="Only TRIGGERED alarms can be acknowledged")

    now = datetime.now(timezone.utc)
    assignment = await _current_pending_assignment(db, alarm_id)
    if assignment is not None and _user_matches_assignment(user, assignment):
        result = await db.execute(
            update(AlarmAssignment)
            .where(AlarmAssignment.id == assignment.id, AlarmAssignment.outcome == AssignmentOutcome.PENDING)
            .values(outcome=AssignmentOutcome.ACCEPTED, responded_at=now, target_user_id=user.id)
        )
        if result.rowcount:
            await record_event(
                db, alarm.id, AlarmEventType.ASSIGNMENT_ACCEPTED, actor_user_id=user.id,
                metadata={"assignment_id": str(assignment.id), "tier": assignment.tier},
            )

    alarm.status = AlarmStatus.ACKNOWLEDGED
    alarm.acknowledged_at = now
    await record_event(db, alarm.id, AlarmEventType.ALARM_ACKNOWLEDGED, actor_user_id=user.id)
    await db.commit()
    await db.refresh(alarm)
    return alarm


@alarms_router.post("/{alarm_id}/archive", response_model=AlarmResponse)
async def archive_alarm(
    alarm_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> Alarm:
    """Hide a completed alarm without deleting its record or chart evidence."""
    alarm = await db.get(Alarm, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_object_visible(alarm.object_id, user)
    if alarm.status not in (AlarmStatus.ACKNOWLEDGED, AlarmStatus.RESOLVED):
        raise HTTPException(status_code=400, detail="Only completed alarms can be archived")
    alarm.status = AlarmStatus.ARCHIVED
    await record_event(db, alarm.id, AlarmEventType.ALARM_ARCHIVED, actor_user_id=user.id)
    await db.commit()
    await db.refresh(alarm)
    return alarm


# ===================================================================
# Device tokens (FCM)
# ===================================================================

@devices_router.post("/register", response_model=DeviceTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: DeviceTokenRegister, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> DeviceToken:
    """Register (or re-claim) an FCM device token for the current user.

    A token is unique across the table — re-registering the same token
    (app reinstall, token refresh delivered again) updates it in place
    rather than erroring or creating a duplicate row.
    """
    existing = await db.scalar(select(DeviceToken).where(DeviceToken.fcm_token == body.fcm_token))
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.user_id = user.id
        existing.platform = body.platform
        existing.is_active = True
        existing.last_seen_at = now
        await db.commit()
        await db.refresh(existing)
        return existing

    device = DeviceToken(
        user_id=user.id, fcm_token=body.fcm_token, platform=body.platform, is_active=True, last_seen_at=now,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@devices_router.delete("/{device_id}")
async def delete_device(
    device_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    device = await db.get(DeviceToken, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.user_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not your device")
    await db.delete(device)
    await db.commit()
    return {"status": "deleted"}


# ===================================================================
# Escalation policies (admin) — configures the dispatch ladder
# ===================================================================

@escalation_policies_router.get("", response_model=list[EscalationPolicyResponse])
async def list_escalation_policies(
    object_id: UUID | None = Query(None), db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> list[EscalationPolicy]:
    stmt = select(EscalationPolicy)
    if object_id is not None:
        stmt = stmt.where(EscalationPolicy.object_id == object_id)
    result = await db.execute(stmt)
    policies = result.scalars().all()
    for policy in policies:
        await db.refresh(policy, attribute_names=["tiers"])
    return policies


@escalation_policies_router.post("", response_model=EscalationPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_escalation_policy(
    body: EscalationPolicyCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> EscalationPolicy:
    policy = EscalationPolicy(name=body.name, object_id=body.object_id)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    policy.tiers = []
    return policy


@escalation_policies_router.delete("/{policy_id}")
async def delete_escalation_policy(
    policy_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> dict:
    policy = await db.get(EscalationPolicy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Escalation policy not found")
    await db.delete(policy)
    await db.commit()
    return {"status": "deleted"}


@escalation_policies_router.post(
    "/{policy_id}/tiers", response_model=EscalationTierResponse, status_code=status.HTTP_201_CREATED
)
async def create_escalation_tier(
    policy_id: UUID, body: EscalationTierCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> EscalationTier:
    policy = await db.get(EscalationPolicy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Escalation policy not found")
    if body.target_type == EscalationTargetType.USER.value and body.target_user_id is None:
        raise HTTPException(status_code=422, detail="target_user_id is required when target_type='user'")
    if body.target_type == EscalationTargetType.ROLE.value and body.target_role is None:
        raise HTTPException(status_code=422, detail="target_role is required when target_type='role'")
    existing = await db.scalar(
        select(EscalationTier).where(
            EscalationTier.policy_id == policy_id, EscalationTier.tier_order == body.tier_order
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Tier {body.tier_order} already exists for this policy")

    tier = EscalationTier(
        policy_id=policy_id,
        tier_order=body.tier_order,
        timeout_seconds=body.timeout_seconds,
        target_type=body.target_type,
        target_user_id=body.target_user_id if body.target_type == EscalationTargetType.USER.value else None,
        target_role=body.target_role if body.target_type == EscalationTargetType.ROLE.value else None,
    )
    db.add(tier)
    await db.commit()
    await db.refresh(tier)
    return tier


# ===================================================================
# Measurements
# ===================================================================

async def _visible_sensor_or_404(db: AsyncSession, sensor_id: UUID, user: User) -> Sensor:
    sensor = await db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    _check_object_visible(sensor.object_id, user)
    return sensor


@measurements_router.get("/{sensor_id}/measurements", response_model=list[MeasurementResponse])
async def list_measurements(
    sensor_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Measurement]:
    await _visible_sensor_or_404(db, sensor_id, user)
    result = await db.execute(
        select(Measurement)
        .where(Measurement.sensor_id == sensor_id)
        .order_by(Measurement.received_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


# Hard ceiling on rows pulled from the DB for a single aggregation request,
# regardless of the requested time window. Chosen generously above any
# realistic reporting rate over the widest supported range (7D) so real
# charts never get truncated by it.
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
    user: User = Depends(get_current_user),
) -> list[Measurement]:
    """Chart data endpoint. Aggregates readings in [since, until] down to
    ~target_points columns instead of returning a fixed number of raw
    points — the frontend sizes target_points from its actual rendered
    chart width, so a phone and a desktop chart get comparable column
    density instead of one being sparse or the other overcrowded.
    """
    await _visible_sensor_or_404(db, sensor_id, user)
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
# Notification Profiles + Endpoints — admin only (configuration surface)
# ===================================================================

@notifications_router.get("/{object_id}/notification-profile", response_model=NotificationProfileResponse)
async def get_notification_profile(
    object_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
) -> NotificationProfile:
    profile = await db.scalar(
        select(NotificationProfile).where(NotificationProfile.object_id == object_id)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Notification profile not found")
    return profile


@notifications_router.post("/{object_id}/notification-profile", response_model=NotificationProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_profile(
    object_id: UUID, body: NotificationProfileCreate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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
    object_id: UUID, body: NotificationProfileUpdate, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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


@notifications_router.get("/{object_id}/notification-endpoints", response_model=list[NotificationEndpointResponse])
async def list_notification_endpoints(
    object_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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
    _admin: User = Depends(require_admin),
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
    _admin: User = Depends(require_admin),
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
    object_id: UUID, endpoint_id: UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
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
