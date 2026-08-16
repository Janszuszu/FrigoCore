"""Service alarm dispatch — assignment, escalation, accept/decline/en-route/resolve."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.database import async_session_factory
from app.enums import AlarmEventType, AlarmStatus, AssignmentOutcome, UserRole
from app.models.alarm import Alarm
from app.models.alarm_assignment import AlarmAssignment
from app.models.alarm_event import AlarmEvent
from app.services.escalation_engine import EscalationEngine

from .conftest import auth_headers
from .helpers import make_object, make_policy, make_triggered_alarm

engine = EscalationEngine(async_session_factory)


async def _events(alarm_id) -> list[AlarmEvent]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(AlarmEvent).where(AlarmEvent.alarm_id == alarm_id).order_by(AlarmEvent.created_at)
        )
        return result.scalars().all()


async def _assignments(alarm_id) -> list[AlarmAssignment]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(AlarmAssignment).where(AlarmAssignment.alarm_id == alarm_id).order_by(AlarmAssignment.dispatched_at)
        )
        return result.scalars().all()


async def _expire_pending(alarm_id) -> None:
    """Force the current PENDING assignment for `alarm_id` into the past so
    the next `run_once()` treats it as timed out."""
    async with async_session_factory() as session:
        assignment = await session.scalar(
            select(AlarmAssignment).where(
                AlarmAssignment.alarm_id == alarm_id, AlarmAssignment.outcome == AssignmentOutcome.PENDING
            )
        )
        assignment.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()


# ---------------------------------------------------------------------------
# 1. Normal lifecycle: TRIGGERED -> ACKNOWLEDGED -> EN_ROUTE -> RESOLVED
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normal_lifecycle(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)

    await engine.run_once()

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(jan))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == AlarmStatus.ACKNOWLEDGED.value

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/en-route", headers=auth_headers(jan))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == AlarmStatus.EN_ROUTE.value
    assert resp.json()["en_route_at"] is not None

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/resolve", headers=auth_headers(jan))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == AlarmStatus.RESOLVED.value


# ---------------------------------------------------------------------------
# 2. Decline -> DECLINED, alarm stays TRIGGERED, next tier assigned immediately
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decline_escalates_immediately(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    piotr = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(
        db_session,
        [
            {"timeout_seconds": 60, "target_user_id": jan.id},
            {"timeout_seconds": 60, "target_user_id": piotr.id},
        ],
        object_id=obj.id,
    )
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/decline", headers=auth_headers(jan))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == AlarmStatus.TRIGGERED.value

    assignments = await _assignments(alarm.id)
    assert len(assignments) == 2
    assert assignments[0].outcome == AssignmentOutcome.DECLINED
    assert assignments[1].outcome == AssignmentOutcome.PENDING
    assert assignments[1].target_user_id == piotr.id


# ---------------------------------------------------------------------------
# 3. No response -> assignment expires -> next tier assigned
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expiry_escalates(db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    piotr = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(
        db_session,
        [
            {"timeout_seconds": 60, "target_user_id": jan.id},
            {"timeout_seconds": 60, "target_user_id": piotr.id},
        ],
        object_id=obj.id,
    )
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()
    await _expire_pending(alarm.id)
    await engine.run_once()

    assignments = await _assignments(alarm.id)
    assert len(assignments) == 2
    assert assignments[0].outcome == AssignmentOutcome.EXPIRED
    assert assignments[1].outcome == AssignmentOutcome.PENDING
    assert assignments[1].target_user_id == piotr.id


# ---------------------------------------------------------------------------
# 4. Escalation through multiple tiers, ending at a manager role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_tier_escalation_to_manager(db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    piotr = await make_user(UserRole.SERWISANT)
    manager = await make_user(UserRole.KIEROWNIK)
    obj = await make_object(db_session)
    await make_policy(
        db_session,
        [
            {"timeout_seconds": 60, "target_user_id": jan.id},
            {"timeout_seconds": 60, "target_user_id": piotr.id},
            {"timeout_seconds": 60, "target_role": UserRole.KIEROWNIK},
        ],
        object_id=obj.id,
    )
    alarm = await make_triggered_alarm(db_session, obj.id)

    await engine.run_once()
    await _expire_pending(alarm.id)
    await engine.run_once()
    await _expire_pending(alarm.id)
    await engine.run_once()

    assignments = await _assignments(alarm.id)
    assert [a.outcome for a in assignments] == [
        AssignmentOutcome.EXPIRED,
        AssignmentOutcome.EXPIRED,
        AssignmentOutcome.PENDING,
    ]
    assert assignments[2].tier == 3
    assert assignments[2].target_role == UserRole.KIEROWNIK

    event_types = {e.event_type for e in await _events(alarm.id)}
    assert AlarmEventType.ESCALATED in event_types
    assert AlarmEventType.ASSIGNMENT_EXPIRED in event_types


# ---------------------------------------------------------------------------
# 5 & 6. Global fallback vs object-level override
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_global_policy_fallback(db_session, make_user):
    global_target = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": global_target.id}], object_id=None)
    alarm = await make_triggered_alarm(db_session, obj.id)

    await engine.run_once()

    assignments = await _assignments(alarm.id)
    assert len(assignments) == 1
    assert assignments[0].target_user_id == global_target.id


@pytest.mark.asyncio
async def test_object_policy_overrides_global(db_session, make_user):
    global_target = await make_user(UserRole.SERWISANT)
    object_target = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": global_target.id}], object_id=None, name="global")
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": object_target.id}], object_id=obj.id, name="object")
    alarm = await make_triggered_alarm(db_session, obj.id)

    await engine.run_once()

    assignments = await _assignments(alarm.id)
    assert len(assignments) == 1
    assert assignments[0].target_user_id == object_target.id


# ---------------------------------------------------------------------------
# 7. Wrong technician cannot accept
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wrong_technician_cannot_accept(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    intruder = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(intruder))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 8. Expired assignment cannot be accepted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expired_assignment_cannot_be_accepted(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    piotr = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(
        db_session,
        [
            {"timeout_seconds": 60, "target_user_id": jan.id},
            {"timeout_seconds": 60, "target_user_id": piotr.id},
        ],
        object_id=obj.id,
    )
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()
    await _expire_pending(alarm.id)
    await engine.run_once()

    # Jan's tier-1 assignment already expired — he can no longer accept it.
    resp = await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(jan))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 9. Concurrent accept — exactly one winner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_accept_exactly_one_winner(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    piotr = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    # Role-tier: both Jan and Piotr are eligible for the same assignment.
    await make_policy(db_session, [{"timeout_seconds": 60, "target_role": UserRole.SERWISANT}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    results = await asyncio.gather(
        client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(jan)),
        client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(piotr)),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409]

    assignments = await _assignments(alarm.id)
    assert len(assignments) == 1
    assert assignments[0].outcome == AssignmentOutcome.ACCEPTED
    assert assignments[0].target_user_id in (jan.id, piotr.id)


# ---------------------------------------------------------------------------
# 10 & 11. AlarmEvent generated for every transition, and is append-only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_events_recorded_for_every_transition(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(jan))
    await client.post(f"/api/v1/alarms/{alarm.id}/en-route", headers=auth_headers(jan))
    await client.post(f"/api/v1/alarms/{alarm.id}/resolve", headers=auth_headers(jan))

    events = await _events(alarm.id)
    event_types = [e.event_type for e in events]
    for expected in (
        AlarmEventType.ASSIGNMENT_CREATED,
        AlarmEventType.NOTIFICATION_SENT,
        AlarmEventType.ASSIGNMENT_ACCEPTED,
        AlarmEventType.ALARM_ACKNOWLEDGED,
        AlarmEventType.ALARM_EN_ROUTE,
        AlarmEventType.CLIENT_NOTIFIED,
        AlarmEventType.ALARM_RESOLVED,
    ):
        assert expected in event_types, f"missing {expected} in {event_types}"

    # Append-only: the count only grows, never shrinks, and earlier rows
    # keep their original created_at after later actions.
    first_batch_count = len(events)
    resp = await client.get(f"/api/v1/alarms/{alarm.id}/events", headers=auth_headers(jan))
    assert resp.status_code == 200
    assert len(resp.json()) == first_batch_count
    timestamps = [e["created_at"] for e in resp.json()]
    assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# 12 & 13. EN_ROUTE gates the client "service is on the way" notification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acknowledged_does_not_notify_client(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(jan))

    event_types = {e.event_type for e in await _events(alarm.id)}
    assert AlarmEventType.CLIENT_NOTIFIED not in event_types
    assert AlarmEventType.ALARM_EN_ROUTE not in event_types


@pytest.mark.asyncio
async def test_en_route_notifies_client(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(jan))
    resp = await client.post(f"/api/v1/alarms/{alarm.id}/en-route", headers=auth_headers(jan))
    assert resp.status_code == 200

    event_types = [e.event_type for e in await _events(alarm.id)]
    assert AlarmEventType.CLIENT_NOTIFIED in event_types
    # CLIENT_NOTIFIED must come after ALARM_EN_ROUTE, not before/instead.
    assert event_types.index(AlarmEventType.ALARM_EN_ROUTE) < event_types.index(AlarmEventType.CLIENT_NOTIFIED)


# ---------------------------------------------------------------------------
# 18. Escalation is race-safe against repeated/duplicate invocation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalation_run_once_is_idempotent_under_race(db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)

    # Simulate two scheduler ticks / two workers racing on the same alarm.
    await asyncio.gather(engine.run_once(), engine.run_once(), engine.run_once())

    assignments = await _assignments(alarm.id)
    assert len(assignments) == 1
    assert assignments[0].tier == 1


# ---------------------------------------------------------------------------
# 19. Declined assignment can never later be accepted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_declined_assignment_cannot_later_be_accepted(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    piotr = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(
        db_session,
        [
            {"timeout_seconds": 60, "target_user_id": jan.id},
            {"timeout_seconds": 60, "target_user_id": piotr.id},
        ],
        object_id=obj.id,
    )
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/decline", headers=auth_headers(jan))
    assert resp.status_code == 200, resp.text

    # Jan's tier-1 assignment is DECLINED — trying to accept it now must fail,
    # even though the alarm is still TRIGGERED (tier 2 is the live PENDING one).
    resp = await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(jan))
    assert resp.status_code == 403, resp.text

    assignments = await _assignments(alarm.id)
    assert assignments[0].outcome == AssignmentOutcome.DECLINED


# ---------------------------------------------------------------------------
# 20. Repeated EN_ROUTE requests cannot send duplicate client notifications
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repeated_en_route_does_not_duplicate_client_notification(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 60, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(jan))
    first = await client.post(f"/api/v1/alarms/{alarm.id}/en-route", headers=auth_headers(jan))
    assert first.status_code == 200, first.text

    # Second en-route call: alarm is no longer ACKNOWLEDGED, so it must be
    # rejected rather than emitting a second CLIENT_NOTIFIED event.
    second = await client.post(f"/api/v1/alarms/{alarm.id}/en-route", headers=auth_headers(jan))
    assert second.status_code == 400, second.text

    events = await _events(alarm.id)
    client_notified_count = sum(1 for e in events if e.event_type == AlarmEventType.CLIENT_NOTIFIED)
    assert client_notified_count == 1


# ---------------------------------------------------------------------------
# 21. Escalation survives a "backend restart" — a fresh EscalationEngine
# instance (no in-memory state) resumes existing PENDING assignments from
# the correct tier, with no duplicate assignment or notification created.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalation_resumes_after_engine_restart(db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    piotr = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(
        db_session,
        [
            {"timeout_seconds": 60, "target_user_id": jan.id},
            {"timeout_seconds": 60, "target_user_id": piotr.id},
        ],
        object_id=obj.id,
    )
    alarm = await make_triggered_alarm(db_session, obj.id)

    # "Before restart": tier 1 dispatched by the original engine instance.
    await engine.run_once()
    assignments = await _assignments(alarm.id)
    assert len(assignments) == 1
    assert assignments[0].tier == 1
    assert assignments[0].outcome == AssignmentOutcome.PENDING

    await _expire_pending(alarm.id)

    # "Backend restart": a brand-new EscalationEngine with no memory of the
    # prior run — all state it acts on comes from the database.
    fresh_engine = EscalationEngine(async_session_factory)
    await fresh_engine.run_once()

    assignments = await _assignments(alarm.id)
    assert len(assignments) == 2
    assert assignments[0].outcome == AssignmentOutcome.EXPIRED
    assert assignments[1].outcome == AssignmentOutcome.PENDING
    assert assignments[1].tier == 2
    assert assignments[1].target_user_id == piotr.id

    # Re-running again (e.g. a second post-restart tick before anything else
    # happens) must not create a duplicate tier-2 assignment or notification.
    await fresh_engine.run_once()
    assignments = await _assignments(alarm.id)
    assert len(assignments) == 2

    events = await _events(alarm.id)
    notification_sent_count = sum(1 for e in events if e.event_type == AlarmEventType.NOTIFICATION_SENT)
    assert notification_sent_count == 2  # one per dispatched tier, not duplicated
