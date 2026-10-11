"""FrigoCore — Measurement model (temperature reading from MQTT)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.sensor import Sensor


class Measurement(Base, UUIDMixin):
    """A single temperature reading received via MQTT."""

    __tablename__ = "measurements"
    # Every chart, stopwatch and consumption query asks for one sensor over a
    # time range; this index serves them all (and any sensor-only lookup).
    __table_args__ = (Index("ix_measurements_sensor_id_received_at", "sensor_id", "received_at"),)

    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Foreign key
    sensor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    sensor: Mapped["Sensor"] = relationship("Sensor", back_populates="measurements")

    def __repr__(self) -> str:
        return f"<Measurement sensor={self.sensor_id} temp={self.temperature} at={self.received_at}>"