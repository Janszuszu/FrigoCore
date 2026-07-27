"""FrigoCore — Notification profile per Object."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.object import Object


class NotificationProfile(Base, UUIDMixin, TimestampMixin):
    """Notification delivery configuration for an Object.

    Each object has exactly one notification profile.
    Contains channel-specific configuration (Telegram bot token, email SMTP, etc.).
    """

    __tablename__ = "notification_profiles"

    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # Channel flags — which channels are enabled for this object
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fcm_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Channel-specific configuration stored as JSONB for flexibility
    telegram_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    fcm_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    email_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sms_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    webhook_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Foreign key — one-to-one with Object
    object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # Relationships
    object: Mapped["Object"] = relationship("Object", back_populates="notification_profile")

    def __repr__(self) -> str:
        return f"<NotificationProfile {self.name!r} object={self.object_id}>"