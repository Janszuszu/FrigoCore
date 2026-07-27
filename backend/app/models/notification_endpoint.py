"""FrigoCore — Notification endpoint (one delivery target per channel).

A NotificationProfile can have multiple endpoints of the same channel type
(e.g. two Telegram chats, three FCM device tokens).
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import NotificationChannel
from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.notification_profile import NotificationProfile


class NotificationEndpoint(Base, UUIDMixin, TimestampMixin):
    """A single notification delivery target.

    Each endpoint belongs to one NotificationProfile and uses one channel.
    Multiple endpoints of the same channel type are allowed per profile.
    """

    __tablename__ = "notification_endpoints"

    channel: Mapped[NotificationChannel] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(256), default="", nullable=False, comment="Human-readable label, e.g. 'Manager phone'")

    # Channel-specific configuration (JSONB for flexibility).
    # Examples:
    #   Telegram → {"chat_id": "123456", "token": "..."}
    #   FCM      → {"device_token": "abc123", "project_id": "..."}
    #   Email    → {"to": ["ops@example.com"], "smtp_server": "smtp.example.com"}
    #   SMS      → {"phone_number": "+48123456789", "provider": "twilio"}
    #   Webhook  → {"url": "https://hooks.example.com/alerts", "secret": "..."}
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Foreign key
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    profile: Mapped["NotificationProfile"] = relationship("NotificationProfile", back_populates="endpoints")

    def __repr__(self) -> str:
        return f"<NotificationEndpoint {self.channel!r} label={self.label!r}>"