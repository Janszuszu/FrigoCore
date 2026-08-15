"""FrigoCore — User model (Admin / Serwisant / Użytkownik)."""

import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import UserRole
from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.object import Object


# Many-to-many: a "user" role can be assigned to several objects; admin and
# serwisant ignore this table entirely (they see every object by role alone).
user_objects = Table(
    "user_objects",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("object_id", ForeignKey("objects.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base, UUIDMixin, TimestampMixin):
    """System user.

    Admin      → full access, sees and can edit everything.
    Serwisant  → read access to every object's dashboard + alarms, can acknowledge alarms.
    User       → read access to only the objects assigned via `objects`.
    """

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(256), default="")

    role: Mapped[UserRole] = mapped_column(String(16), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    objects: Mapped[List["Object"]] = relationship(
        "Object", secondary=user_objects, back_populates="users"
    )

    def __repr__(self) -> str:
        return f"<User {self.username!r} role={self.role}>"
