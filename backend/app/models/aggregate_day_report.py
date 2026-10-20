"""FrigoCore — An aggregate's analysed day (daily report).

Once a day, just after midnight, the power (or current) trace of each
aggregate that has one is cut into run and rest periods
(app/services/power_cycles.py) and summed up here, one row per aggregate
per local calendar day.
"""

import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import JSON, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class AggregateDayReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "aggregate_day_reports"
    __table_args__ = (UniqueConstraint("aggregate_id", "day", name="uq_aggregate_day_reports_aggregate_day"),)

    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aggregates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="Local (Europe/Warsaw) calendar day")
    # "power" (W) or "current" (A) — which trace the day was read from.
    source: Mapped[str] = mapped_column(String(16), nullable=False)

    running_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idle_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    starts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_run_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_run_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_idle_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duty_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    covered_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    energy_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_running_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="W or A while running")
    avg_start_peak: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Every run of the day: [[running, start, end, complete]].
    runs: Mapped[list[list[Any]]] = mapped_column(JSON, nullable=False, default=list)

    def __repr__(self) -> str:
        return f"<AggregateDayReport aggregate={self.aggregate_id} day={self.day}>"
