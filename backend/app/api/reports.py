"""FrigoCore — Reports (Raport) API.

Reads the receiver day reports written every night by
app/services/daily_reports.py. Anyone who can see the object can read them.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.routes import _check_object_visible
from app.database import get_db
from app.models.object import Object
from app.models.receiver import Receiver
from app.models.receiver_day_report import ReceiverDayReport
from app.models.user import User
from app.schemas import ObjectDayReportResponse, ReceiverDayReportResponse

reports_router = APIRouter()

# How many past days the day picker offers.
MAX_DAYS = 62


@reports_router.get("/{object_id}/reports/receivers", response_model=ObjectDayReportResponse)
async def receiver_day_reports(
    object_id: UUID,
    day: date | None = Query(None, description="Local day; the newest reported day when left out"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ObjectDayReportResponse:
    _check_object_visible(object_id, user)
    if await db.get(Object, object_id) is None:
        raise HTTPException(status_code=404, detail="Object not found")

    days = list((await db.scalars(
        select(ReceiverDayReport.day)
        .join(Receiver, Receiver.id == ReceiverDayReport.receiver_id)
        .where(Receiver.object_id == object_id)
        .distinct()
        .order_by(ReceiverDayReport.day.desc())
        .limit(MAX_DAYS)
    )).all())
    shown = day or (days[0] if days else None)
    if shown is None:
        return ObjectDayReportResponse(day=None, days=[], receivers=[])

    rows = (await db.execute(
        select(ReceiverDayReport, Receiver.name)
        .join(Receiver, Receiver.id == ReceiverDayReport.receiver_id)
        .where(Receiver.object_id == object_id, ReceiverDayReport.day == shown)
        .order_by(Receiver.display_order, Receiver.name)
    )).all()
    return ObjectDayReportResponse(
        day=shown,
        days=days,
        receivers=[
            ReceiverDayReportResponse(
                receiver_id=r.receiver_id,
                name=name,
                day=r.day,
                cooling_count=r.cooling_count,
                cooling_seconds=r.cooling_seconds,
                idle_count=r.idle_count,
                idle_seconds=r.idle_seconds,
                duty_percent=r.duty_percent,
                defrost_count=r.defrost_count,
                covered_seconds=r.covered_seconds,
                min_temp=r.min_temp,
                avg_temp=r.avg_temp,
                max_temp=r.max_temp,
                defrosts=r.defrosts,
                off_periods=r.off_periods,
            )
            for r, name in rows
        ],
    )
