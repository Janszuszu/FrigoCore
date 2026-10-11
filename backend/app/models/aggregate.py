"""FrigoCore — Aggregate (agregat) model.

An aggregate is a condensing unit as the service technician knows it: its
nameplate data (compressor model, refrigerant and its charge, installation
date) plus a hand-picked group of the object's sensors — outdoor
temperature, discharge or suction line and so on. An object may have
several aggregates, and one sensor (typically the outdoor one) may belong to
more than one of them.

Like receivers, aggregates are presentation only — alarms keep using each
sensor's own AlarmConfig thresholds.
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.sensor import Sensor


class Aggregate(Base, UUIDMixin, TimestampMixin):
    """A condensing unit belonging to one Object."""

    __tablename__ = "aggregates"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    compressor_model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    refrigerant: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="Refrigerant designation, e.g. R404A"
    )
    refrigerant_charge_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    installed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    sensor_links: Mapped[list["AggregateSensor"]] = relationship(
        back_populates="aggregate",
        cascade="all, delete-orphan",
        order_by="AggregateSensor.position",
        lazy="selectin",
    )

    @property
    def sensor_ids(self) -> list[uuid.UUID]:
        return [link.sensor_id for link in self.sensor_links]

    def __repr__(self) -> str:
        return f"<Aggregate name={self.name!r}>"


class AggregateSensor(Base):
    """One sensor shown on an aggregate, in the technician's order."""

    __tablename__ = "aggregate_sensors"

    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aggregates.id", ondelete="CASCADE"), primary_key=True
    )
    # Deleting a sensor simply drops it from every aggregate.
    sensor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sensors.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    aggregate: Mapped[Aggregate] = relationship(back_populates="sensor_links")
    sensor: Mapped["Sensor"] = relationship("Sensor", lazy="selectin")
