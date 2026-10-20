"""FrigoCore — Reports (Raport) API.

Reads the receiver and aggregate day reports written every night by
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
from app.models.aggregate import Aggregate
from app.models.aggregate_day_report import AggregateDayReport
from app.models.object import Object
from app.models.receiver import Receiver
from app.models.receiver_day_report import ReceiverDayReport
from app.models.user import User
from app.schemas import AggregateDayReportResponse, ObjectDayReportResponse, ReceiverDayReportResponse

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

    receiver_days = set((await db.scalars(
        select(ReceiverDayReport.day)
        .join(Receiver, Receiver.id == ReceiverDayReport.receiver_id)
        .where(Receiver.object_id == object_id)
        .distinct()
    )).all())
    aggregate_days = set((await db.scalars(
        select(AggregateDayReport.day)
        .join(Aggregate, Aggregate.id == AggregateDayReport.aggregate_id)
        .where(Aggregate.object_id == object_id)
        .distinct()
    )).all())
    days = sorted(receiver_days | aggregate_days, reverse=True)[:MAX_DAYS]
    shown = day or (days[0] if days else None)
    if shown is None:
        return ObjectDayReportResponse(day=None, days=[], receivers=[])

    rows = (await db.execute(
        select(ReceiverDayReport, Receiver.name)
        .join(Receiver, Receiver.id == ReceiverDayReport.receiver_id)
        .where(Receiver.object_id == object_id, ReceiverDayReport.day == shown)
        .order_by(Receiver.display_order, Receiver.name)
    )).all()
    aggregate_rows = (await db.execute(
        select(AggregateDayReport, Aggregate.name)
        .join(Aggregate, Aggregate.id == AggregateDayReport.aggregate_id)
        .where(Aggregate.object_id == object_id, AggregateDayReport.day == shown)
        .order_by(Aggregate.display_order, Aggregate.name)
    )).all()
    return ObjectDayReportResponse(
        day=shown,
        days=days,
        aggregates=[
            AggregateDayReportResponse(
                aggregate_id=a.aggregate_id,
                name=name,
                day=a.day,
                source=a.source,
                running_seconds=a.running_seconds,
                idle_seconds=a.idle_seconds,
                starts=a.starts,
                avg_run_seconds=a.avg_run_seconds,
                max_run_seconds=a.max_run_seconds,
                avg_idle_seconds=a.avg_idle_seconds,
                duty_percent=a.duty_percent,
                covered_seconds=a.covered_seconds,
                energy_kwh=a.energy_kwh,
                avg_running_value=a.avg_running_value,
            )
            for a, name in aggregate_rows
        ],
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
