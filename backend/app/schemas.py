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


# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------

class SensorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    mqtt_topic: str = Field(..., min_length=1, max_length=512, description="MQTT topic exactly as configured by admin")
    offline_timeout_seconds: int = Field(120, ge=10, le=3600)


class SensorUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    mqtt_topic: str | None = Field(None, min_length=1, max_length=512)
    offline_timeout_seconds: int | None = Field(None, ge=10, le=3600)
    is_active: bool | None = None


class SensorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    mqtt_topic: str
    current_temperature: float | None
    last_message_at: datetime | None
    offline_timeout_seconds: int
    is_active: bool
    object_id: UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AlarmConfig
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

class AlarmAcknowledge(BaseModel):
    pass  # No extra fields needed


class AlarmResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alarm_type: str
    status: str
    trigger_value: float | None
    detected_at: datetime
    triggered_at: datetime | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    description: str
    object_id: UUID
    sensor_id: UUID | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# NotificationProfile
# ---------------------------------------------------------------------------

class NotificationProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


class NotificationProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    object_id: UUID
    created_at: datetime
    updated_at: datetime


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