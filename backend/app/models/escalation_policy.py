"""FrigoCore — EscalationPolicy / EscalationTier.

A policy is an ordered ladder of tiers used to dispatch a TRIGGERED alarm.
Resolution priority when an alarm needs dispatching:

    object-level policy (EscalationPolicy.object_id == alarm.object_id)
    -> global default policy (EscalationPolicy.object_id IS NULL)

NOTE: the product spec also describes a "client level" tier between object
and global. This codebase has no Client/organization entity distinct from
Object, so that tier has no home to resolve against — implementing it would
mean inventing an unrelated entity. Only object-level and global resolution
are implemented; see conversation for the explicit call-out.
"""

import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import EscalationTargetType, UserRole
from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.object import Object
    from app.models.user import User


class EscalationPolicy(Base, UUIDMixin, TimestampMixin):
    """An ordered escalation ladder. object_id NULL = global default policy."""

    __tablename__ = "escalation_policies"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    object_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    object: Mapped[Optional["Object"]] = relationship("Object")
    tiers: Mapped[List["EscalationTier"]] = relationship(
        "EscalationTier",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="EscalationTier.tier_order",
    )

    def __repr__(self) -> str:
        scope = f"object={self.object_id}" if self.object_id else "GLOBAL"
        return f"<EscalationPolicy {self.name!r} {scope}>"


class EscalationTier(Base, UUIDMixin, TimestampMixin):
    """One ordered rung of an EscalationPolicy's ladder."""

    __tablename__ = "escalation_tiers"
    __table_args__ = (
        UniqueConstraint("policy_id", "tier_order", name="uq_escalation_tier_order"),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("escalation_policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier_order: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    target_type: Mapped[EscalationTargetType] = mapped_column(String(16), nullable=False)
    target_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    target_role: Mapped[Optional[UserRole]] = mapped_column(String(16), nullable=True)

    # Relationships
    policy: Mapped["EscalationPolicy"] = relationship("EscalationPolicy", back_populates="tiers")
    target_user: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:
        target = self.target_user_id or self.target_role
        return f"<EscalationTier policy={self.policy_id} order={self.tier_order} target={target}>"
