"""FrigoCore — Dispatch Service.

Shared logic for turning a TRIGGERED alarm into a technician assignment and
walking it through the escalation ladder. Used by both the EscalationEngine
(background loop) and the API layer (accept/decline endpoints), so the two
never duplicate — or drift from — how a tier is resolved and dispatched.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    AlarmEventType,
    AssignmentOutcome,
    EscalationTargetType,
    UserRole,
)
from app.models.alarm import Alarm
from app.models.alarm_assignment import AlarmAssignment
from app.models.alarm_event import AlarmEvent
from app.models.device_token import DeviceToken
from app.models.escalation_policy import EscalationPolicy, EscalationTier
from app.models.object import Object
from app.models.user import User
from app.services.notification_engine import NotificationEngine

logger = logging.getLogger(__name__)


async def record_event(
    session: AsyncSession,
    alarm_id,
    event_type: AlarmEventType,
    actor_user_id=None,
    message: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AlarmEvent:
    """Append one immutable audit-trail row. Never call session.execute(update())
    or delete() against alarm_events — this table is append-only by design."""
    event = AlarmEvent(
        alarm_id=alarm_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        message=message,
        event_metadata=metadata,
    )
    session.add(event)
    await session.flush()
    return event


async def resolve_policy(session: AsyncSession, object_id) -> Optional[EscalationPolicy]:
    """object-level policy -> global default policy (object_id IS NULL).

    Only two levels are resolved. The product spec also describes a
    "client level" tier between object and global; this codebase has no
    Client/organization entity distinct from Object to resolve that against,
    so it is intentionally not implemented (see conversation).
    """
    object_policy = await session.scalar(
        select(EscalationPolicy)
        .where(EscalationPolicy.object_id == object_id, EscalationPolicy.is_active == True)
        .order_by(EscalationPolicy.created_at.desc())
    )
    if object_policy is not None:
        await session.refresh(object_policy, attribute_names=["tiers"])
        return object_policy

    global_policy = await session.scalar(
        select(EscalationPolicy)
        .where(EscalationPolicy.object_id.is_(None), EscalationPolicy.is_active == True)
        .order_by(EscalationPolicy.created_at.asc())
    )
    if global_policy is not None:
        await session.refresh(global_policy, attribute_names=["tiers"])
    return global_policy


async def _device_tokens_for_tier(session: AsyncSession, tier: EscalationTier) -> tuple[list[DeviceToken], Optional[User]]:
    """Return (device_tokens, resolved_target_user_for_USER_tier)."""
    if tier.target_type == EscalationTargetType.USER:
        user = await session.get(User, tier.target_user_id)
        if user is None or not user.is_active:
            return [], user
        tokens = (
            await session.execute(
                select(DeviceToken).where(DeviceToken.user_id == user.id, DeviceToken.is_active == True)
            )
        ).scalars().all()
        return list(tokens), user

    # ROLE tier — every active user holding the role
    users = (
        await session.execute(select(User).where(User.role == tier.target_role, User.is_active == True))
    ).scalars().all()
    if not users:
        return [], None
    tokens = (
        await session.execute(
            select(DeviceToken).where(
                DeviceToken.user_id.in_([u.id for u in users]), DeviceToken.is_active == True
            )
        )
    ).scalars().all()
    return list(tokens), None


async def dispatch_tier(
    session: AsyncSession,
    alarm: Alarm,
    tier: EscalationTier,
) -> AlarmAssignment:
    """Create the AlarmAssignment for one tier, push to targets, log events.

    Relies on the DB-level partial unique index (one PENDING assignment per
    alarm) to guarantee this never races into two live assignments — if two
    callers hit this concurrently for the same alarm, the second INSERT
    raises IntegrityError, which the caller must treat as "already dispatched".
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=tier.timeout_seconds)

    assignment = AlarmAssignment(
        alarm_id=alarm.id,
        tier=tier.tier_order,
        target_user_id=tier.target_user_id if tier.target_type == EscalationTargetType.USER else None,
        target_role=tier.target_role if tier.target_type == EscalationTargetType.ROLE else None,
        outcome=AssignmentOutcome.PENDING,
        dispatched_at=now,
        expires_at=expires_at,
    )
    session.add(assignment)
    await session.flush()

    await record_event(
        session,
        alarm.id,
        AlarmEventType.ASSIGNMENT_CREATED,
        message=f"Tier {tier.tier_order} assignment created",
        metadata={
            "assignment_id": str(assignment.id),
            "tier": tier.tier_order,
            "target_type": tier.target_type.value if hasattr(tier.target_type, "value") else str(tier.target_type),
            "target_user_id": str(tier.target_user_id) if tier.target_user_id else None,
            "target_role": tier.target_role.value if hasattr(tier.target_role, "value") else tier.target_role,
        },
    )

    device_tokens, _ = await _device_tokens_for_tier(session, tier)
    obj = await session.get(Object, alarm.object_id)
    try:
        await NotificationEngine.send_service_alarm_dispatch(alarm, obj, assignment, device_tokens)
        await record_event(
            session,
            alarm.id,
            AlarmEventType.NOTIFICATION_SENT,
            message=f"Service alarm push sent to {len(device_tokens)} device(s)",
            metadata={"assignment_id": str(assignment.id), "device_count": len(device_tokens)},
        )
    except Exception:
        logger.exception("Failed to dispatch service alarm push for assignment %s", assignment.id)

    return assignment


async def start_dispatch(session: AsyncSession, alarm: Alarm) -> Optional[AlarmAssignment]:
    """Create the first (tier 1) assignment for a newly TRIGGERED alarm."""
    policy = await resolve_policy(session, alarm.object_id)
    if policy is None or not policy.tiers:
        await record_event(
            session,
            alarm.id,
            AlarmEventType.ESCALATION_EXHAUSTED,
            message="No escalation policy configured for this object or globally",
        )
        return None
    first_tier = policy.tiers[0]
    return await dispatch_tier(session, alarm, first_tier)


async def escalate(
    session: AsyncSession,
    alarm: Alarm,
    previous_tier_order: int,
    reason: str,
) -> Optional[AlarmAssignment]:
    """Dispatch the next tier after `previous_tier_order`, or record exhaustion."""
    policy = await resolve_policy(session, alarm.object_id)
    if policy is None:
        await record_event(
            session, alarm.id, AlarmEventType.ESCALATION_EXHAUSTED,
            message="No escalation policy resolvable at escalation time",
        )
        return None

    next_tier = next((t for t in policy.tiers if t.tier_order == previous_tier_order + 1), None)
    if next_tier is None:
        await record_event(
            session,
            alarm.id,
            AlarmEventType.ESCALATION_EXHAUSTED,
            message=f"No tier configured after tier {previous_tier_order}",
            metadata={"previous_tier": previous_tier_order, "reason": reason},
        )
        return None

    await record_event(
        session,
        alarm.id,
        AlarmEventType.ESCALATED,
        message=f"Escalating from tier {previous_tier_order} to tier {next_tier.tier_order} ({reason})",
        metadata={"previous_tier": previous_tier_order, "next_tier": next_tier.tier_order, "reason": reason},
    )
    return await dispatch_tier(session, alarm, next_tier)
