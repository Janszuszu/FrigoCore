"""FrigoCore — Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Object
# ---------------------------------------------------------------------------

class ObjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256, description="Human-readable display name")
    description: str = Field("", max_length=5000)


class ObjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = Field(None, max_length=5000)
    is_active: bool | None = None


class ObjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Rollups the administration list needs to render a row without having
    # to expand it first. Derived, never stored.
    sensor_count: int = 0
    online_sensor_count: int = 0


# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------

# Icon identifiers are validated as slugs rather than against a fixed list,
# so the frontend's icon library can grow without a backend release.
ICON_PATTERN = r"^[a-z0-9][a-z0-9-]{0,31}$"

# Calibration is a trim for sensor drift, not a way to relabel a reading.
CALIBRATION_LIMIT = 20.0


class SensorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    mqtt_topic: str = Field(..., min_length=1, max_length=512, description="MQTT topic exactly as configured by admin")
    offline_timeout_seconds: int = Field(120, ge=10, le=3600)
    icon: str = Field("thermometer", pattern=ICON_PATTERN)
    calibration_offset: float = Field(0.0, ge=-CALIBRATION_LIMIT, le=CALIBRATION_LIMIT)


class SensorUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    mqtt_topic: str | None = Field(None, min_length=1, max_length=512)
    offline_timeout_seconds: int | None = Field(None, ge=10, le=3600)
    is_active: bool | None = None
    icon: str | None = Field(None, pattern=ICON_PATTERN)
    display_order: int | None = Field(None, ge=0, le=9999)
    calibration_offset: float | None = Field(None, ge=-CALIBRATION_LIMIT, le=CALIBRATION_LIMIT)


class SensorReorder(BaseModel):
    """Full ordering for one object's sensors, first to last.

    The whole list is sent rather than a single position so the resulting
    order is unambiguous and applies to every client viewing the object.
    """

    sensor_ids: list[UUID] = Field(..., min_length=1)


class SensorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    mqtt_topic: str
    current_temperature: float | None
    last_message_at: datetime | None
    offline_timeout_seconds: int
    is_active: bool
    icon: str
    display_order: int
    calibration_offset: float
    object_id: UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AlarmConfig (legacy, normalized)
# ---------------------------------------------------------------------------

class AlarmConfigCreate(BaseModel):
    alarm_type: str = Field(..., pattern=r"^(high_temperature|low_temperature|offline)$")
    threshold_value: float | None = None
    trigger_delay_seconds: int = Field(300, ge=0, le=86400)
    is_enabled: bool = True


class AlarmConfigUpdate(BaseModel):
    threshold_value: float | None = None
    trigger_delay_seconds: int | None = Field(None, ge=0, le=86400)
    is_enabled: bool | None = None


class AlarmConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alarm_type: str
    threshold_value: float | None
    trigger_delay_seconds: int
    is_enabled: bool
    sensor_id: UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

class MeasurementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    temperature: float
    received_at: datetime
    sensor_id: UUID


# ---------------------------------------------------------------------------
# Alarm
# ---------------------------------------------------------------------------

class AlarmResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alarm_type: str
    status: str
    trigger_value: float | None
    detected_at: datetime
    triggered_at: datetime | None
    acknowledged_at: datetime | None
    en_route_at: datetime | None
    resolved_at: datetime | None
    description: str
    object_id: UUID
    object_name: str
    sensor_id: UUID | None
    sensor_name: str
    notification_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Alarm dispatch — assignments, events, escalation policies, device tokens
# ---------------------------------------------------------------------------

class AlarmAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alarm_id: UUID
    tier: int
    target_user_id: UUID | None
    target_role: str | None
    outcome: str
    dispatched_at: datetime
    delivered_at: datetime | None
    responded_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


class AlarmEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alarm_id: UUID
    event_type: str
    actor_user_id: UUID | None
    message: str | None
    event_metadata: dict | None
    created_at: datetime


class DeviceTokenRegister(BaseModel):
    fcm_token: str = Field(..., min_length=1, max_length=512)
    platform: str = Field(..., pattern=r"^(android|ios)$")


class DeviceTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    platform: str
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EscalationTierCreate(BaseModel):
    tier_order: int = Field(..., ge=1)
    timeout_seconds: int = Field(..., ge=1, le=86400)
    target_type: str = Field(..., pattern=r"^(user|role)$")
    target_user_id: UUID | None = None
    target_role: str | None = Field(None, pattern=r"^(admin|serwisant|kierownik|user)$")


class EscalationTierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    tier_order: int
    timeout_seconds: int
    target_type: str
    target_user_id: UUID | None
    target_role: str | None


class EscalationPolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    object_id: UUID | None = Field(None, description="Omit/null for the global default policy")


class EscalationPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    object_id: UUID | None
    is_active: bool
    tiers: list[EscalationTierResponse] = []


# ---------------------------------------------------------------------------
# NotificationProfile
# ---------------------------------------------------------------------------

class NotificationProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


class NotificationProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)


class NotificationProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    object_id: UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# User (accounts + auth)
# ---------------------------------------------------------------------------

ROLE_PATTERN = r"^(admin|serwisant|user)$"


class UserResponse(BaseModel):
    """hashed_password is deliberately absent from every response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    object_ids: list[UUID] = Field(default_factory=list)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    email: str = Field(..., min_length=1, max_length=320)
    full_name: str = Field("", max_length=256)
    password: str = Field(..., min_length=8, max_length=256)
    role: str = Field(..., pattern=ROLE_PATTERN)
    object_ids: list[UUID] = Field(default_factory=list)


class UserUpdate(BaseModel):
    email: str | None = Field(None, min_length=1, max_length=320)
    full_name: str | None = Field(None, max_length=256)
    role: str | None = Field(None, pattern=ROLE_PATTERN)
    is_active: bool | None = None
    object_ids: list[UUID] | None = None


class UserPasswordSet(BaseModel):
    password: str = Field(..., min_length=8, max_length=256)


class ObjectUserAssign(BaseModel):
    user_id: UUID


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---------------------------------------------------------------------------
# NotificationEndpoint
# ---------------------------------------------------------------------------

class NotificationEndpointCreate(BaseModel):
    channel: str = Field(..., pattern=r"^(telegram|fcm|email|sms|webhook)$")
    label: str = Field("", max_length=256)
    config: dict = Field(default_factory=dict)
    is_enabled: bool = True


class NotificationEndpointUpdate(BaseModel):
    label: str | None = Field(None, max_length=256)
    config: dict | None = None
    is_enabled: bool | None = None


class NotificationEndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: str
    label: str
    config: dict
    is_enabled: bool
    profile_id: UUID
    created_at: datetime
    updated_at: datetime