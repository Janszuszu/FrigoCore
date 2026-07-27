"""FrigoCore — Measurement model (temperature reading from MQTT)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.sensor import Sensor


class Measurement(Base, UUIDMixin):
    """A single temperature reading received via MQTT."""

    __tablename__ = "measurements"

    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Foreign key
    sensor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    sensor: Mapped["Sensor"] = relationship("Sensor", back_populates="measurements")

    def __repr__(self) -> str:
        return f"<Measurement sensor={self.sensor_id} temp={self.temperature} at={self.received_at}>"