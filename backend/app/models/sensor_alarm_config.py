"""FrigoCore — Flat alarm configuration per sensor.

Each sensor has exactly one row with all alarm settings denormalized.
This replaces the previous normalized approach (one row per alarm type).

Fields:
  - high_enabled / high_temperature / high_delay
  - low_enabled  / low_temperature  / low_delay
  - offline_enabled / offline_timeout / offline_delay
"""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.sensor import Sensor


class SensorAlarmConfig(Base, UUIDMixin, TimestampMixin):
    """Flat alarm configuration — one row per sensor."""

    __tablename__ = "sensor_alarm_configs"

    # ── HIGH temperature alarm ────────────────────────────────────────
    high_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    high_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Threshold °C")
    high_delay: Mapped[int] = mapped_column(Integer, default=300, nullable=False, comment="Delay in seconds before alarm fires")

    # ── LOW temperature alarm ─────────────────────────────────────────
    low_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    low_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Threshold °C")
    low_delay: Mapped[int] = mapped_column(Integer, default=300, nullable=False, comment="Delay in seconds before alarm fires")

    # ── OFFLINE alarm ─────────────────────────────────────────────────
    offline_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    offline_timeout: Mapped[int] = mapped_column(Integer, default=120, nullable=False, comment="Seconds without message before OFFLINE is detected")
    offline_delay: Mapped[int] = mapped_column(Integer, default=300, nullable=False, comment="Additional delay in seconds before alarm fires")

    # Foreign key — one config per sensor
    sensor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )

    # Relationships
    sensor: Mapped["Sensor"] = relationship("Sensor", back_populates="alarm_config_flat")

    def __repr__(self) -> str:
        return f"<SensorAlarmConfig sensor={self.sensor_id}>"