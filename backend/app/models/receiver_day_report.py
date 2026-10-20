"""FrigoCore — A receiver's analysed day (daily report).

Once a day, just after midnight, the day that has ended is cut into
cooling runs, idle runs and defrosts (app/services/daily_cycles.py) and the
outcome is kept here, one row per receiver per local calendar day. The
report screens read these rows; nothing is recomputed on request.
"""

import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import JSON, Date, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ReceiverDayReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "receiver_day_reports"
    __table_args__ = (UniqueConstraint("receiver_id", "day", name="uq_receiver_day_reports_receiver_day"),)

    receiver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("receivers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="Local (Europe/Warsaw) calendar day")

    cooling_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooling_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idle_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idle_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duty_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    defrost_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    covered_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_temp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_temp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_temp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # [{"start", "end", "peak", "recovery_seconds"}], ISO times in UTC.
    defrosts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    # Long warm-ups — switched off or failing: [{"start", "end", "peak"}].
    off_periods: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    # Every run of the day, for charts later: [[kind, start, end, start_temp, end_temp]].
    runs: Mapped[list[list[Any]]] = mapped_column(JSON, nullable=False, default=list)

    def __repr__(self) -> str:
        return f"<ReceiverDayReport receiver={self.receiver_id} day={self.day}>"
