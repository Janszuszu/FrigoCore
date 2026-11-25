"""A tier with no logged-in phone is skipped at once; admin may accept any
alarm (2026-11-25: a test alarm went to a technician with no phone and the
admin's phone got 403 on PRZYJĄŁEM)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database import async_session_factory
from app.enums import AlarmStatus, AssignmentOutcome, UserRole
from app.models.alarm_assignment import AlarmAssignment
from app.services.escalation_engine import EscalationEngine

from .conftest import auth_headers
from .helpers import make_object, make_policy, make_triggered_alarm

engine = EscalationEngine(async_session_factory)


async def _assignments(alarm_id) -> list[AlarmAssignment]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(AlarmAssignment).where(AlarmAssignment.alarm_id == alarm_id).order_by(AlarmAssignment.tier)
        )
        return result.scalars().all()


@pytest.mark.asyncio
async def test_tier_without_phone_escalates_on_next_cycle(db_session, make_user):
    no_phone = await make_user(UserRole.SERWISANT, with_phone=False)
    piotr = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(
        db_session,
        [
            {"timeout_seconds": 300, "target_user_id": no_phone.id},
            {"timeout_seconds": 300, "target_user_id": piotr.id},
        ],
        object_id=obj.id,
    )
    alarm = await make_triggered_alarm(db_session, obj.id)

    await engine.run_once()  # tier 1 created, unreachable -> expires now
    await engine.run_once()  # next cycle moves on, no 5-minute wait

    assignments = await _assignments(alarm.id)
    assert [a.outcome for a in assignments] == [AssignmentOutcome.EXPIRED, AssignmentOutcome.PENDING]
    assert assignments[1].target_user_id == piotr.id


@pytest.mark.asyncio
async def test_last_tier_without_phone_keeps_its_timeout(db_session, make_user):
    no_phone = await make_user(UserRole.SERWISANT, with_phone=False)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 300, "target_user_id": no_phone.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)

    await engine.run_once()
    await engine.run_once()

    assignments = await _assignments(alarm.id)
    assert [a.outcome for a in assignments] == [AssignmentOutcome.PENDING]


@pytest.mark.asyncio
async def test_admin_accepts_alarm_assigned_to_technician(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 300, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(admin))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == AlarmStatus.EN_ROUTE.value

    assignments = await _assignments(alarm.id)
    assert assignments[0].outcome == AssignmentOutcome.ACCEPTED
    assert assignments[0].target_user_id == admin.id

    # The technician is too late now.
    resp = await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(jan))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_other_technician_still_refused_in_polish(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    piotr = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 300, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/accept", headers=auth_headers(piotr))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Ten alarm jest teraz przydzielony komuś innemu"


@pytest.mark.asyncio
async def test_web_acknowledge_goes_en_route_and_closes_assignment(client, db_session, make_user):
    jan = await make_user(UserRole.SERWISANT)
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session)
    await make_policy(db_session, [{"timeout_seconds": 300, "target_user_id": jan.id}], object_id=obj.id)
    alarm = await make_triggered_alarm(db_session, obj.id)
    await engine.run_once()

    resp = await client.post(f"/api/v1/alarms/{alarm.id}/acknowledge", headers=auth_headers(admin))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == AlarmStatus.EN_ROUTE.value
    assert resp.json()["en_route_at"] is not None
    assert (await _assignments(alarm.id))[0].outcome == AssignmentOutcome.ACCEPTED
