"""FrigoCore — Sensor model.

Every sensor belongs to exactly one Object.
The MQTT topic is auto-generated:  {object.slug}/{sensor.slug}
Both slugs are immutable — renaming the display name does NOT affect MQTT routing.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.alarm_config import AlarmConfig
    from app.models.measurement import Measurement
    from app.models.object import Object


class Sensor(Base, UUIDMixin, TimestampMixin):
    """Sensor belonging to exactly one Object."""

    __tablename__ = "sensors"

    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="Human-readable display name")
    slug: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True,
        comment="Immutable topic suffix, e.g. 'komora-1'"
    )

    # Live telemetry (denormalized for fast reads)
    current_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Sensor-level OFFLINE detection timeout (seconds).
    # After this many seconds without an MQTT message, the sensor is considered OFFLINE.
    offline_timeout_seconds: Mapped[int] = mapped_column(
        Integer, default=120, nullable=False,
        comment="Seconds without MQTT message before OFFLINE is detected"
    )

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
        return f"<Sensor slug={self.slug!r} name={self.name!r}>"