"""FrigoCore — Notification profile per Object.

Each Object has exactly one NotificationProfile.
The profile can contain multiple endpoints per channel (e.g. 2 Telegram bots,
3 FCM devices, a webhook, etc.).
"""

import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.notification_endpoint import NotificationEndpoint
    from app.models.object import Object


class NotificationProfile(Base, UUIDMixin, TimestampMixin):
    """A collection of notification endpoints for one Object."""

    __tablename__ = "notification_profiles"

    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # Foreign key — one-to-one with Object
    object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # Relationships
    object: Mapped["Object"] = relationship("Object", back_populates="notification_profile")
    endpoints: Mapped[List["NotificationEndpoint"]] = relationship(
        "NotificationEndpoint", back_populates="profile", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<NotificationProfile {self.name!r} object={self.object_id}>"