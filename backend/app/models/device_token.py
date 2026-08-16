"""FrigoCore — DeviceToken (FCM push registration).

A user may register several devices (phone + tablet, or a reinstall that
hasn't cleared the old token yet), so this is User 1 -> N DeviceToken, not
a single token column on User.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import DevicePlatform
from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class DeviceToken(Base, UUIDMixin, TimestampMixin):
    """One registered push-notification device for a User."""

    __tablename__ = "device_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fcm_token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    platform: Mapped[DevicePlatform] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="device_tokens")

    def __repr__(self) -> str:
        return f"<DeviceToken user={self.user_id} platform={self.platform}>"
