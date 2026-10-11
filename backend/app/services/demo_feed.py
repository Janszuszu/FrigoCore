"""FrigoCore — live synthetic readings for demonstration objects.

The Google Play reviewers (and anyone shown the app) log in to an account
whose object must look alive: charts for the last 24 h, a cooling cycle on
the stopwatches, a week of electricity use. Its sensors use MQTT topics
under ``demo/`` — a namespace no real gateway can publish to (EMQX lets the
gateways write only to ``frigo/#``) — and this loop feeds them a reading a
minute, computed from the clock, so the data never runs dry.

A sensor is fed when its topic is ``demo/<anything>/<signal>`` and
``<signal>`` is one of SIGNALS; anything else is left alone. After a pause
(deploy, restart) the gap is filled in so the charts have no holes.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.measurement import Measurement
from app.models.sensor import Sensor

logger = logging.getLogger(__name__)

DEMO_TOPIC_PREFIX = "demo/"
FEED_INTERVAL_SECONDS = 60
BACKFILL_STEP = timedelta(minutes=2)
BACKFILL_LIMIT = timedelta(days=7)

# Cycles of the two refrigerated spaces: period and cooling time in seconds,
# then the controller's cut-in and cut-out temperatures (°C).
FREEZER = (25 * 60, 12 * 60, -19.9, -22.1)
COLD_ROOM = (60 * 60, 19 * 60, 5.7, 3.5)
# Electrical load (W): standby, freezer compressor, cold room compressor.
BASE_W, FREEZER_W, COLD_ROOM_W = 25.0, 950.0, 800.0
# The energy counter starts from zero at this instant (2026-09-21).
COUNTER_EPOCH = 1_790_000_000


def _phase(t: float, period: int, cooling: int) -> tuple[bool, float]:
    """Whether the compressor runs at t, and how far (0..1) into that phase."""
    p = t % period
    if p < cooling:
        return True, p / cooling
    return False, (p - cooling) / (period - cooling)


def _chamber(t: float, cycle: tuple[int, int, float, float]) -> tuple[float, bool, float]:
    """Air temperature falls from cut-in to cut-out while cooling and climbs back while idle."""
    period, cooling, cut_in, cut_out = cycle
    running, f = _phase(t, period, cooling)
    temperature = cut_in + (cut_out - cut_in) * f if running else cut_out + (cut_in - cut_out) * f
    return temperature, running, f


def _cooling_seconds(t: float, cycle: tuple[int, int, float, float]) -> float:
    """Compressor running time from the counter epoch up to t."""
    period, cooling, _, _ = cycle

    def until(x: float) -> float:
        return (x // period) * cooling + min(x % period, cooling)

    return until(t) - until(COUNTER_EPOCH)


def _freezer_evaporator(t: float) -> float:
    chamber, running, f = _chamber(t, FREEZER)
    # Well below the air while running; drifting back up to it while idle.
    return chamber - 6.0 if running else chamber - 0.3 - 3.0 * (1 - f)


def _cold_room_evaporator(t: float) -> float:
    chamber, running, f = _chamber(t, COLD_ROOM)
    return chamber - 10.0 if running else chamber - 9.0 * (1 - f) ** 2


def _outdoor(t: float) -> float:
    local_hour = (t / 3600 + 2) % 24  # CEST is close enough for a daily swing
    return 12.0 + 6.0 * math.sin(2 * math.pi * (local_hour - 9) / 24)


def _running(t: float) -> tuple[bool, bool]:
    return _chamber(t, FREEZER)[1], _chamber(t, COLD_ROOM)[1]


def _power(t: float) -> float:
    freezer, cold_room = _running(t)
    return BASE_W + FREEZER_W * freezer + COLD_ROOM_W * cold_room


def _voltage(t: float) -> float:
    return 231.0 + 2.5 * math.sin(t / 700)


def _energy(t: float) -> float:
    joules = BASE_W * (t - COUNTER_EPOCH) + FREEZER_W * _cooling_seconds(t, FREEZER) \
        + COLD_ROOM_W * _cooling_seconds(t, COLD_ROOM)
    return joules / 3.6e6


def _discharge(t: float) -> float:
    return 35.0 + 30.0 * any(_running(t))


SIGNALS = {
    "0": lambda t: _chamber(t, COLD_ROOM)[0],   # Komora chłodnicza
    "1": lambda t: _chamber(t, FREEZER)[0],     # Mroźnia
    "chlodnia-parownik": _cold_room_evaporator,
    "mroznia-parownik": _freezer_evaporator,
    "zewnetrzna": _outdoor,
    "tloczenie": _discharge,
    "moc": _power,
    "napiecie": _voltage,
    "prad": lambda t: _power(t) / _voltage(t),
    "energia": _energy,
}


def signal_for(topic: str):
    if not topic.startswith(DEMO_TOPIC_PREFIX):
        return None
    return SIGNALS.get(topic.rsplit("/", 1)[-1])


async def feed_once(session: AsyncSession, now: datetime | None = None) -> int:
    """Write the reading due now for every demo sensor, first filling any
    gap since its last one. Returns how many readings were written."""
    now = now or datetime.now(timezone.utc)
    sensors = (await session.execute(
        select(Sensor).where(Sensor.mqtt_topic.like(f"{DEMO_TOPIC_PREFIX}%"))
    )).scalars().all()
    written = 0
    for sensor in sensors:
        signal = signal_for(sensor.mqtt_topic)
        if signal is None:
            continue
        last = await session.scalar(
            select(func.max(Measurement.received_at)).where(Measurement.sensor_id == sensor.id)
        )
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)  # SQLite keeps naive UTC
        at = max(last + BACKFILL_STEP, now - BACKFILL_LIMIT) if last else now - BACKFILL_LIMIT
        while at < now:
            session.add(Measurement(sensor_id=sensor.id, temperature=round(signal(at.timestamp()), 3), received_at=at))
            written += 1
            at += BACKFILL_STEP
        value = round(signal(now.timestamp()), 3)
        session.add(Measurement(sensor_id=sensor.id, temperature=value, received_at=now))
        sensor.current_temperature = value
        sensor.last_message_at = now
        written += 1
    await session.commit()
    return written


class DemoFeed:
    """Feeds the demo sensors once a minute."""

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
                    written = await feed_once(session)
                if written > 1:
                    logger.debug("[Demo] wrote %d readings", written)
            except Exception:
                # A failed round must not stop the feed.
                logger.exception("[Demo] feeding demo sensors failed")
            await asyncio.sleep(FEED_INTERVAL_SECONDS)
