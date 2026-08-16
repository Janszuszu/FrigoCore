"""FrigoCore — Alarm model (triggered or pending alert)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import AlarmStatus, AlarmType
from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.alarm_assignment import AlarmAssignment
    from app.models.alarm_event import AlarmEvent
    from app.models.object import Object
    from app.models.sensor import Sensor


class Alarm(Base, UUIDMixin, TimestampMixin):
    """A concrete alarm instance linked to an Object and triggered by a Sensor.

    Lifecycle: PENDING → TRIGGERED → ACKNOWLEDGED → EN_ROUTE → RESOLVED → ARCHIVED
    """

    __tablename__ = "alarms"

    alarm_type: Mapped[AlarmType] = mapped_column(String(32), nullable=False)
    status: Mapped[AlarmStatus] = mapped_column(String(32), default=AlarmStatus.PENDING, nullable=False)

    # Value that triggered the alarm (e.g. 8.5 °C for HIGH temp)
    trigger_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # When the condition was first detected
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # When the alarm was actually triggered after the delay
    triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the alarm was acknowledged by a user
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the technician marked themselves as travelling to the site
    en_route_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the alarm condition cleared
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Foreign keys
    object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    object: Mapped["Object"] = relationship("Object", back_populates="alarms")
    sensor: Mapped[Optional["Sensor"]] = relationship("Sensor")
    assignments: Mapped[List["AlarmAssignment"]] = relationship(
        "AlarmAssignment", back_populates="alarm", cascade="all, delete-orphan",
        order_by="AlarmAssignment.dispatched_at",
    )
    events: Mapped[List["AlarmEvent"]] = relationship(
        "AlarmEvent", back_populates="alarm", cascade="all, delete-orphan",
        order_by="AlarmEvent.created_at",
    )

    def __repr__(self) -> str:
        return f"<Alarm {self.alarm_type!r} status={self.status} object={self.object_id}>"