"""FrigoCore — Sensor model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.alarm_config import AlarmConfig
    from app.models.measurement import Measurement
    from app.models.object import Object


class Sensor(Base, UUIDMixin, TimestampMixin):
    """Sensor belonging to exactly one Object.

    Each sensor is identified by an MQTT topic combining Object + Sensor.
    """

    __tablename__ = "sensors"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    mqtt_topic: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    # Live telemetry (denormalized for fast reads)
    current_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Foreign key — every sensor belongs to one object
    object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    object: Mapped["Object"] = relationship("Object", back_populates="sensors")
    measurements: Mapped[List["Measurement"]] = relationship(
        "Measurement", back_populates="sensor", cascade="all, delete-orphan"
    )
    alarm_configs: Mapped[List["AlarmConfig"]] = relationship(
        "AlarmConfig", back_populates="sensor", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Sensor {self.name!r} topic={self.mqtt_topic!r}>"