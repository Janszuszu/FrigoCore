"""FrigoCore — electricity used, from an energy meter's kWh counter.

An energy meter reports an ever-growing kWh counter, so a day's
consumption is how far the counter moved since the end of the previous day
(or since its first reading that day, when the previous day has no data). A
counter that went backwards — a replaced or reset meter — counts only that
day's own movement instead of producing a negative day.

Days are cut at local midnight: the owner reads "today" in Polish time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.measurement import Measurement

ENERGY_TIMEZONE = ZoneInfo("Europe/Warsaw")


def local_today() -> date:
    return datetime.now(ENERGY_TIMEZONE).date()


async def _day_range(db: AsyncSession, sensor_id: UUID, day: date) -> tuple[float | None, float | None]:
    start = datetime.combine(day, time.min, ENERGY_TIMEZONE).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, ENERGY_TIMEZONE).astimezone(timezone.utc)
    row = (await db.execute(
        select(func.min(Measurement.temperature), func.max(Measurement.temperature)).where(
            Measurement.sensor_id == sensor_id,
            Measurement.received_at >= start,
            Measurement.received_at < end,
        )
    )).one()
    return row[0], row[1]


async def daily_usage(db: AsyncSession, sensor_id: UUID, first_day: date, last_day: date) -> dict[date, float]:
    """kWh used on each day in [first_day, last_day]; days without readings
    are left out."""
    _, previous_max = await _day_range(db, sensor_id, first_day - timedelta(days=1))
    usage: dict[date, float] = {}
    day = first_day
    while day <= last_day:
        day_min, day_max = await _day_range(db, sensor_id, day)
        if day_max is None:
            previous_max = None
        else:
            if previous_max is not None and day_max >= previous_max:
                used = day_max - previous_max
            else:
                used = day_max - day_min
            usage[day] = round(used, 3)
            previous_max = day_max
        day += timedelta(days=1)
    return usage


@dataclass(frozen=True, slots=True)
class Consumption:
    """Usage over the periods the clients show, plus every day from the
    start of the earlier of this week and this month, up to today."""

    today_kwh: float | None
    week_kwh: float | None
    month_kwh: float | None
    days: dict[date, float]


def period_start(today: date) -> date:
    """The first day the clients need: Monday of this week or the 1st of
    this month, whichever is earlier."""
    return min(today - timedelta(days=today.weekday()), today.replace(day=1))


def summarize(days: dict[date, float], today: date) -> Consumption:
    monday = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def total(first: date) -> float | None:
        values = [kwh for day, kwh in days.items() if first <= day <= today]
        return round(sum(values), 3) if values else None

    return Consumption(
        today_kwh=days.get(today),
        week_kwh=total(monday),
        month_kwh=total(month_start),
        days=days,
    )


async def consumption(db: AsyncSession, sensor_id: UUID, today: date | None = None) -> Consumption:
    today = today or local_today()
    return summarize(await daily_usage(db, sensor_id, period_start(today), today), today)


def combine(parts: list[Consumption], today: date) -> Consumption:
    """Several meters added up day by day."""
    days: dict[date, float] = {}
    for part in parts:
        for day, kwh in part.days.items():
            days[day] = round(days.get(day, 0.0) + kwh, 3)
    return summarize(days, today)
