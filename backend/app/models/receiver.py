"""FrigoCore — Receiver (odbiornik) model.

A receiver is one refrigerated space — a cold room, freezer or display
case — as the owner thinks of it. It doesn't measure anything itself: it
points at the object's chamber sensor and, optionally, the evaporator
sensor, and carries the working temperatures the controller is set to.
From those two traces the backend infers whether the receiver is cooling,
idle or defrosting (app/services/receiver_state.py).

The working temperatures are presentation only — alarms keep using each
sensor's own AlarmConfig thresholds.
"""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.sensor import Sensor


class Receiver(Base, UUIDMixin, TimestampMixin):
    """A refrigerated space belonging to one Object."""

    __tablename__ = "receivers"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Deleting a sensor leaves the receiver in place with an unknown state
    # rather than silently removing the owner's configuration.
    chamber_sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True,
        comment="Air temperature inside the chamber",
    )
    evaporator_sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True,
        comment="Evaporator coil temperature; without it defrost can't be told apart",
    )

    setpoint: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Temperature the chamber should hold, °C"
    )
    cut_in: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Chamber temperature at which cooling starts, °C"
    )
    cut_out: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Chamber temperature at which cooling stops, °C"
    )

    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    chamber_sensor: Mapped[Optional["Sensor"]] = relationship(
        "Sensor", foreign_keys=[chamber_sensor_id], lazy="selectin"
    )
    evaporator_sensor: Mapped[Optional["Sensor"]] = relationship(
        "Sensor", foreign_keys=[evaporator_sensor_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Receiver name={self.name!r}>"
