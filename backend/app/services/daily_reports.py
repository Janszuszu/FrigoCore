"""FrigoCore — Nightly receiver day reports.

Just after local midnight every active receiver's finished day is run
through app/services/daily_cycles.py and stored as a ReceiverDayReport.
Days missed while the backend was down are caught up on start (up to
BACKFILL_DAYS back); a day already stored is never recomputed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.measurement import Measurement
from app.models.receiver import Receiver
from app.models.receiver_day_report import ReceiverDayReport
from app.services.daily_cycles import MAX_GAP, DayAnalysis, analyze_day
from app.services.energy import ENERGY_TIMEZONE, local_today
from app.services.receiver_state import Point

logger = logging.getLogger(__name__)

BACKFILL_DAYS = 7
# Run a few minutes past midnight, so the day's last readings have landed.
RUN_AFTER_MIDNIGHT = timedelta(minutes=5)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of a local calendar day in UTC (23 or 25 hours on DST days)."""
    start = datetime.combine(day, time.min, ENERGY_TIMEZONE).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, ENERGY_TIMEZONE).astimezone(timezone.utc)
    return start, end


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite stores naive UTC


async def _readings(db: AsyncSession, sensor_id: UUID | None, start: datetime, end: datetime) -> list[Point]:
    if sensor_id is None:
        return []
    rows = await db.execute(
        select(Measurement.received_at, Measurement.temperature)
        .where(
            Measurement.sensor_id == sensor_id,
            Measurement.received_at >= start - MAX_GAP,
            Measurement.received_at < end,
        )
        .order_by(Measurement.received_at.asc())
    )
    return [(_aware(t), v) for t, v in rows.all()]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def to_report(receiver_id: UUID, day: date, a: DayAnalysis) -> ReceiverDayReport:
    return ReceiverDayReport(
        receiver_id=receiver_id,
        day=day,
        cooling_count=len(a.cooling_runs),
        cooling_seconds=a.cooling_seconds,
        idle_count=len(a.idle_runs),
        idle_seconds=a.idle_seconds,
        duty_percent=a.duty_percent,
        defrost_count=len(a.defrosts),
        covered_seconds=a.covered_seconds,
        min_temp=a.min_temp,
        avg_temp=a.avg_temp,
        max_temp=a.max_temp,
        defrosts=[
            {"start": _iso(d.start), "end": _iso(d.end), "peak": d.peak, "recovery_seconds": d.recovery_seconds}
            for d in a.defrosts
        ],
        off_periods=[
            {"start": _iso(r.start), "end": _iso(r.end), "peak": round(r.end_temp, 1)}
            for r in a.runs if r.kind == "off"
        ],
        runs=[[r.kind, _iso(r.start), _iso(r.end), round(r.start_temp, 1), round(r.end_temp, 1)] for r in a.runs],
    )


async def build_report(db: AsyncSession, receiver: Receiver, day: date) -> ReceiverDayReport:
    start, end = day_bounds(day)
    chamber = await _readings(db, receiver.chamber_sensor_id, start, end)
    evaporator = await _readings(db, receiver.evaporator_sensor_id, start, end)
    # The CPU-bound analysis runs off the event loop so MQTT ingestion
    # isn't held up while a day is being cut into cycles.
    analysis = await asyncio.to_thread(
        analyze_day, chamber, evaporator or None, start, end, receiver.cut_in, receiver.cut_out
    )
    return to_report(receiver.id, day, analysis)


async def run_pending(db: AsyncSession, today: date | None = None) -> int:
    """Stores every missing report of the last BACKFILL_DAYS finished days.
    Returns how many were written."""
    today = today or local_today()
    days = [today - timedelta(days=n) for n in range(BACKFILL_DAYS, 0, -1)]
    receivers = (await db.scalars(
        select(Receiver).where(Receiver.is_active.is_(True), Receiver.chamber_sensor_id.is_not(None))
    )).all()
    done = {
        (rid, d) for rid, d in (await db.execute(
            select(ReceiverDayReport.receiver_id, ReceiverDayReport.day).where(ReceiverDayReport.day >= days[0])
        )).all()
    }
    written = 0
    for receiver in receivers:
        created = _aware(receiver.created_at) if receiver.created_at else None
        for day in days:
            if (receiver.id, day) in done:
                continue
            # No report for days before the receiver was configured.
            if created is not None and day_bounds(day)[1] <= created:
                continue
            db.add(await build_report(db, receiver, day))
            await db.commit()
            written += 1
    return written


def seconds_until_next_run(now: datetime) -> float:
    local = now.astimezone(ENERGY_TIMEZONE)
    next_midnight = datetime.combine(local.date() + timedelta(days=1), time.min, ENERGY_TIMEZONE)
    return max(60.0, (next_midnight + RUN_AFTER_MIDNIGHT - local).total_seconds())


class DailyReports:
    """Writes the day reports after every midnight (and catches up on start)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        while True:
            try:
                async with self._session_factory() as session:
                    written = await run_pending(session)
                if written:
                    logger.info("[Reports] wrote %d receiver day reports", written)
            except Exception:
                # A failed night must not stop the next one.
                logger.exception("[Reports] writing receiver day reports failed")
            await asyncio.sleep(seconds_until_next_run(datetime.now(timezone.utc)))
