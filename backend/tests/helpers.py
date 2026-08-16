"""FrigoCore backend tests — shared model-creation helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AlarmStatus, AlarmType, EscalationTargetType
from app.models.alarm import Alarm
from app.models.escalation_policy import EscalationPolicy, EscalationTier
from app.models.object import Object


async def make_object(db: AsyncSession, name: str = "Test Object") -> Object:
    obj = Object(name=name, description="", is_active=True)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def make_triggered_alarm(db: AsyncSession, object_id) -> Alarm:
    now = datetime.now(timezone.utc)
    alarm = Alarm(
        alarm_type=AlarmType.HIGH_TEMPERATURE,
        status=AlarmStatus.TRIGGERED,
        trigger_value=12.0,
        detected_at=now,
        triggered_at=now,
        description="High temperature alarm — current: 12.0°C",
        object_id=object_id,
        sensor_id=None,
    )
    db.add(alarm)
    await db.commit()
    await db.refresh(alarm)
    return alarm


async def make_policy(
    db: AsyncSession,
    tiers: list[dict],
    object_id=None,
    name: str = "Test Policy",
) -> EscalationPolicy:
    """tiers: list of {"timeout_seconds": int, "target_user_id": UUID} or
    {"timeout_seconds": int, "target_role": UserRole}."""
    policy = EscalationPolicy(name=name, object_id=object_id, is_active=True)
    db.add(policy)
    await db.flush()

    for i, tier in enumerate(tiers, start=1):
        target_user_id = tier.get("target_user_id")
        target_role = tier.get("target_role")
        db.add(
            EscalationTier(
                policy_id=policy.id,
                tier_order=i,
                timeout_seconds=tier["timeout_seconds"],
                target_type=EscalationTargetType.USER if target_user_id else EscalationTargetType.ROLE,
                target_user_id=target_user_id,
                target_role=target_role,
            )
        )
    await db.commit()
    await db.refresh(policy)
    return policy
