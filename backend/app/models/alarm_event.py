"""FrigoCore — AlarmEvent (append-only audit trail).

Every important lifecycle/dispatch transition writes exactly one row here.
Rows are never updated or deleted during normal operation — this table is
what lets the full history of an alarm (who, when, what) be reconstructed.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import AlarmEventType
from app.models.base import Base, UUIDMixin, _utcnow

if TYPE_CHECKING:
    from app.models.alarm import Alarm
    from app.models.user import User


class AlarmEvent(Base, UUIDMixin):
    """One immutable audit-trail entry for an Alarm."""

    __tablename__ = "alarm_events"

    alarm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alarms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[AlarmEventType] = mapped_column(String(32), nullable=False, index=True)

    # Who caused this event — NULL for system-generated events (escalation
    # timeout, auto-resolve, notification dispatch).
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    event_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    # Relationships
    alarm: Mapped["Alarm"] = relationship("Alarm", back_populates="events")
    actor: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:
        return f"<AlarmEvent alarm={self.alarm_id} type={self.event_type}>"
