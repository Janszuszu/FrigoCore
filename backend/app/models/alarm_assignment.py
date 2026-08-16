"""FrigoCore — AlarmAssignment (one dispatch attempt in the escalation ladder).

An Alarm accumulates one AlarmAssignment row per dispatch attempt as it
escalates through tiers. Exactly one row per alarm may be `PENDING`
(actionable) at a time — enforced by a partial unique index in the
migration, not just application logic, so a racing scheduler or two
concurrent accept/decline requests can never leave two live assignments.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import AssignmentOutcome, UserRole
from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.alarm import Alarm
    from app.models.user import User


class AlarmAssignment(Base, UUIDMixin, TimestampMixin):
    """A single dispatch attempt of an Alarm to one escalation tier's target."""

    __tablename__ = "alarm_assignments"

    alarm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alarms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False)

    # Resolved target — a role-tier assignment leaves target_user_id NULL and
    # any active user holding target_role may accept it; the first accept
    # wins (atomic UPDATE ... WHERE outcome='pending').
    target_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_role: Mapped[Optional[UserRole]] = mapped_column(String(16), nullable=True)

    outcome: Mapped[AssignmentOutcome] = mapped_column(
        String(16), default=AssignmentOutcome.PENDING, nullable=False, index=True
    )

    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Relationships
    alarm: Mapped["Alarm"] = relationship("Alarm", back_populates="assignments")
    target_user: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:
        return f"<AlarmAssignment alarm={self.alarm_id} tier={self.tier} outcome={self.outcome}>"
