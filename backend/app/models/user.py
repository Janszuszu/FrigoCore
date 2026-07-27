"""FrigoCore — User model (Admin / Client)."""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import UserRole
from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.object import Object


class User(Base, UUIDMixin, TimestampMixin):
    """System user.

    Admin  → full access, sees all objects.
    Client → dashboard + alarms only, assigned to exactly one object.
    """

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(256), default="")

    role: Mapped[UserRole] = mapped_column(String(16), default=UserRole.CLIENT, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # A Client is assigned to exactly one Object; Admin can see all objects (nullable).
    object_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("objects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    object: Mapped[Optional["Object"]] = relationship("Object", back_populates="users")

    def __repr__(self) -> str:
        return f"<User {self.username!r} role={self.role}>"