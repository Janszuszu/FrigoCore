"""FrigoCore — Escalation Engine.

Periodic background task, structured the same way as AlarmEngine:
  1. Dispatch tier 1 for any TRIGGERED alarm that has no assignment yet.
  2. Expire any PENDING assignment past its expires_at and escalate to the
     next tier.

Each alarm is processed in its own short-lived transaction rather than one
big transaction for the whole cycle. That is what makes duplicate-dispatch
protection work: the partial unique index on alarm_assignments (one PENDING
row per alarm) turns a losing race into an IntegrityError scoped to that
alarm's own transaction, which is caught and treated as "someone else
already handled it" instead of poisoning every other alarm in the cycle.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.enums import AlarmEventType, AlarmStatus, AssignmentOutcome
from app.models.alarm import Alarm
from app.models.alarm_assignment import AlarmAssignment
from app.services.dispatch_service import escalate, record_event, start_dispatch

logger = logging.getLogger(__name__)

EVALUATION_INTERVAL_SECONDS = 5


class EscalationEngine:
    """Periodic background task that dispatches and escalates alarm assignments."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Escalation engine started (interval=%ds)", EVALUATION_INTERVAL_SECONDS)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Escalation engine stopped")

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Escalation engine cycle failed")
            await asyncio.sleep(EVALUATION_INTERVAL_SECONDS)

    async def run_once(self) -> None:
        """One evaluation cycle. Public so tests and the API layer can drive
        it deterministically instead of waiting on the sleep interval."""
        await self._dispatch_undispatched_alarms()
        await self._expire_and_escalate_pending()

    # ------------------------------------------------------------------
    # Step 1 — first dispatch for alarms with no assignment yet
    # ------------------------------------------------------------------
    async def _dispatch_undispatched_alarms(self) -> None:
        async with self._session_factory() as session:
            triggered = (
                await session.execute(select(Alarm.id).where(Alarm.status == AlarmStatus.TRIGGERED))
            ).scalars().all()
            already_assigned = set(
                (
                    await session.execute(
                        select(AlarmAssignment.alarm_id).where(AlarmAssignment.alarm_id.in_(triggered))
                    )
                ).scalars().all()
            ) if triggered else set()

        for alarm_id in triggered:
            if alarm_id in already_assigned:
                continue
            await self._dispatch_one(alarm_id)

    async def _dispatch_one(self, alarm_id) -> None:
        async with self._session_factory() as session:
            try:
                alarm = await session.get(Alarm, alarm_id)
                if alarm is None or alarm.status != AlarmStatus.TRIGGERED:
                    return
                await start_dispatch(session, alarm)
                await session.commit()
            except IntegrityError:
                # Another cycle/worker won the race and already dispatched
                # tier 1 for this alarm — nothing to do.
                await session.rollback()
                logger.info("Dispatch race lost for alarm %s — already assigned", alarm_id)

    # ------------------------------------------------------------------
    # Step 2 — expire timed-out assignments and escalate
    # ------------------------------------------------------------------
    async def _expire_and_escalate_pending(self) -> None:
        async with self._session_factory() as session:
            now = datetime.now(timezone.utc)
            expired_candidates = (
                await session.execute(
                    select(AlarmAssignment.id).where(
                        AlarmAssignment.outcome == AssignmentOutcome.PENDING,
                        AlarmAssignment.expires_at.isnot(None),
                        AlarmAssignment.expires_at <= now,
                    )
                )
            ).scalars().all()

        for assignment_id in expired_candidates:
            await self._expire_one(assignment_id)

    async def _expire_one(self, assignment_id) -> None:
        async with self._session_factory() as session:
            now = datetime.now(timezone.utc)
            # Atomic claim: only succeeds if still PENDING. Guards against
            # this same assignment being expired twice by overlapping cycles,
            # and against a concurrent accept/decline racing the timeout.
            result = await session.execute(
                update(AlarmAssignment)
                .where(AlarmAssignment.id == assignment_id, AlarmAssignment.outcome == AssignmentOutcome.PENDING)
                .values(outcome=AssignmentOutcome.EXPIRED, responded_at=now)
            )
            if result.rowcount == 0:
                await session.rollback()
                return

            assignment = await session.get(AlarmAssignment, assignment_id)
            alarm = await session.get(Alarm, assignment.alarm_id)
            if alarm is None or alarm.status != AlarmStatus.TRIGGERED:
                # Alarm moved on (e.g. resolved) before the timeout fired.
                await session.commit()
                return

            await record_event(
                session,
                alarm.id,
                AlarmEventType.ASSIGNMENT_EXPIRED,
                message=f"Tier {assignment.tier} assignment expired with no response",
                metadata={"assignment_id": str(assignment.id), "tier": assignment.tier},
            )
            try:
                await escalate(session, alarm, previous_tier_order=assignment.tier, reason="timeout")
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.info("Escalation race lost for alarm %s after expiry", alarm.id)
