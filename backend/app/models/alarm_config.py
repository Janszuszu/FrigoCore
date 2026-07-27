"""FrigoCore — Alarm configuration per sensor."""

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import AlarmType
from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.sensor import Sensor


class AlarmConfig(Base, UUIDMixin, TimestampMixin):
    """Threshold and delay configuration for a specific alarm type on a sensor.

    Each sensor can have up to 3 alarm configs (HIGH, LOW, OFFLINE).
    """

    __tablename__ = "alarm_configs"

    alarm_type: Mapped[AlarmType] = mapped_column(String(32), nullable=False)

    # Threshold values (only relevant for HIGH / LOW temperature)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=True)
    # For HIGH: max temp before alarm, for LOW: min temp before alarm, for OFFLINE: seconds without message

    # Delay before the alarm is actually triggered (in seconds)
    # e.g. 300 means 5 minutes of sustained condition before alarm fires
    trigger_delay_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)

    # Offline timeout — seconds without MQTT message that indicate the sensor is offline
    # The OFFLINE alarm fires after (offline_timeout_seconds + trigger_delay_seconds)
    offline_timeout_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=True)

    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Foreign key
    sensor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    sensor: Mapped["Sensor"] = relationship("Sensor", back_populates="alarm_configs")

    @property
    def effective_offline_delay(self) -> timedelta:
        """Total seconds before an OFFLINE alarm fires."""
        if self.alarm_type == AlarmType.OFFLINE:
            return timedelta(
                seconds=(self.offline_timeout_seconds or 0) + self.trigger_delay_seconds
            )
        return timedelta(seconds=self.trigger_delay_seconds)

    def __repr__(self) -> str:
        return f"<AlarmConfig {self.alarm_type!r} sensor={self.sensor_id}>"