"""FrigoCore — Meter (licznik) model.

A meter is an electricity meter as the owner thinks of it: its kWh counter
— from which the backend works out the consumption per day, week and
month (app/services/energy.py) — and, optionally, the instantaneous power,
current and voltage the same meter reports, shown live beside it.

Like receivers and aggregates, meters are presentation only — alarms keep
using each sensor's own AlarmConfig thresholds.
"""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.sensor import Sensor


class Meter(Base, UUIDMixin, TimestampMixin):
    """An electricity meter belonging to one Object."""

    __tablename__ = "meters"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Deleting a sensor leaves the meter in place rather than silently
    # removing the owner's configuration.
    energy_sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True, comment="kWh counter"
    )
    power_sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True
    )
    current_sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True
    )
    voltage_sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True
    )

    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    energy_sensor: Mapped[Optional["Sensor"]] = relationship("Sensor", foreign_keys=[energy_sensor_id], lazy="selectin")
    power_sensor: Mapped[Optional["Sensor"]] = relationship("Sensor", foreign_keys=[power_sensor_id], lazy="selectin")
    current_sensor: Mapped[Optional["Sensor"]] = relationship("Sensor", foreign_keys=[current_sensor_id], lazy="selectin")
    voltage_sensor: Mapped[Optional["Sensor"]] = relationship("Sensor", foreign_keys=[voltage_sensor_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<Meter name={self.name!r}>"
