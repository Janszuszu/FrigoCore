"""FrigoCore — Alarm configuration per sensor.

Each sensor can have up to 3 alarm configs (HIGH, LOW, OFFLINE).
The OFFLINE timeout lives on Sensor.offline_timeout_seconds — this model
only stores the alarm trigger delay.
"""

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

    Three alarm types per sensor:
      - HIGH / LOW  → threshold_value is the temperature boundary
      - OFFLINE      → threshold_value is NULL (uses Sensor.offline_timeout_seconds)

    trigger_delay_seconds — how long the condition must persist before the
    alarm transitions from PENDING → TRIGGERED.
    """

    __tablename__ = "alarm_configs"

    alarm_type: Mapped[AlarmType] = mapped_column(String(32), nullable=False)

    # Temperature threshold (only relevant for HIGH / LOW)
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Delay before the alarm fires (in seconds)
    trigger_delay_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)

    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Foreign key
    sensor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    sensor: Mapped["Sensor"] = relationship("Sensor", back_populates="alarm_configs")

    @property
    def effective_offline_delay(self) -> timedelta:
        """Total seconds before an OFFLINE alarm fires (timeout + trigger delay).

        The OFFLINE timeout is stored on the Sensor, not here.
        """
        if self.alarm_type == AlarmType.OFFLINE and self.sensor is not None:
            return timedelta(
                seconds=self.sensor.offline_timeout_seconds + self.trigger_delay_seconds
            )
        return timedelta(seconds=self.trigger_delay_seconds)

    def __repr__(self) -> str:
        return f"<AlarmConfig {self.alarm_type!r} sensor={self.sensor_id}>"