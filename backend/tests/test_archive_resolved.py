"""POST /alarms/archive-resolved — the mobile app's "clear history" button."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.enums import AlarmStatus, UserRole
from app.models.alarm import Alarm

from .conftest import auth_headers
from .helpers import make_object, make_triggered_alarm


async def _resolved_alarm(db_session, object_id) -> Alarm:
    alarm = await make_triggered_alarm(db_session, object_id)
    alarm.status = AlarmStatus.RESOLVED
    alarm.resolved_at = datetime.now(timezone.utc)
    await db_session.commit()
    return alarm


@pytest.mark.asyncio
async def test_archives_only_resolved_alarms(client, db_session, make_user):
    serwisant = await make_user(UserRole.SERWISANT)
    obj = await make_object(db_session)
    resolved = await _resolved_alarm(db_session, obj.id)
    active = await make_triggered_alarm(db_session, obj.id)

    resp = await client.post("/api/v1/alarms/archive-resolved", headers=auth_headers(serwisant))
    assert resp.status_code == 200, resp.text
    assert resp.json()["archived"] == 1

    await db_session.refresh(resolved)
    await db_session.refresh(active)
    assert resolved.status == AlarmStatus.ARCHIVED
    assert active.status == AlarmStatus.TRIGGERED


@pytest.mark.asyncio
async def test_object_owner_cannot_clear_history(client, db_session, make_user):
    owner = await make_user(UserRole.USER)
    obj = await make_object(db_session)
    resolved = await _resolved_alarm(db_session, obj.id)

    resp = await client.post("/api/v1/alarms/archive-resolved", headers=auth_headers(owner))
    assert resp.status_code == 403

    await db_session.refresh(resolved)
    assert resolved.status == AlarmStatus.RESOLVED
