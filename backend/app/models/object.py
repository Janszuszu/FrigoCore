"""FrigoCore — Object model (monitored facility).

An Object is the top-level entity that groups sensors.
"""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.alarm import Alarm
    from app.models.notification_profile import NotificationProfile
    from app.models.sensor import Sensor
    from app.models.user import User


class Object(Base, UUIDMixin, TimestampMixin):
    """Monitored facility — groups sensors and is assigned to clients."""

    __tablename__ = "objects"

    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="Human-readable display name")
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User", secondary="user_objects", back_populates="objects"
    )
    sensors: Mapped[List["Sensor"]] = relationship("Sensor", back_populates="object", cascade="all, delete-orphan")
    alarms: Mapped[List["Alarm"]] = relationship("Alarm", back_populates="object", cascade="all, delete-orphan")
    notification_profile: Mapped[Optional["NotificationProfile"]] = relationship(
        "NotificationProfile", back_populates="object", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Object name={self.name!r}>"