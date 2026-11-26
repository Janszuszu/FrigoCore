"""FrigoCore — a chamber's door over one day: how often it opened and how
long it stood open in total.

A door is an on/off sensor (kind "door", 1 = open) published by the
gateway every few seconds. It belongs to the chamber whose topic it
extends: "<group>-drzwi" covers the sensors whose topic slug is "<group>"
or "<group>-...", the same convention the defrost bit uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sensor import Sensor
from app.sensor_kinds import SensorKind

DOOR_TOPIC_SUFFIX = "-drzwi"

# A reading stands for the time up to the next one, but no longer than
# this: a door left "open" by a gateway that went quiet is not counted.
MAX_GAP = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class DoorDay:
    openings: int
    open_seconds: int


def _slug(topic: str) -> str:
    return topic.rsplit("/", 1)[-1]


def covers(door_topic: str, sensor_topic: str) -> bool:
    """True when the door sensor belongs to the chamber of `sensor_topic`."""
    door = _slug(door_topic)
    if not door.endswith(DOOR_TOPIC_SUFFIX):
        return False
    group = door[: -len(DOOR_TOPIC_SUFFIX)]
    slug = _slug(sensor_topic)
    return slug == group or slug.startswith(group + "-")


async def door_sensor_for(db: AsyncSession, chamber: Sensor | None) -> Sensor | None:
    """The door sensor of the chamber's object that covers it, if any."""
    if chamber is None:
        return None
    doors = await db.scalars(
        select(Sensor).where(
            Sensor.object_id == chamber.object_id,
            Sensor.kind == SensorKind.DOOR.value,
            Sensor.is_active.is_(True),
        )
    )
    return next((d for d in doors if covers(d.mqtt_topic, chamber.mqtt_topic)), None)


def analyze_door(points: list[tuple[datetime, float]], start: datetime, end: datetime) -> DoorDay:
    """Openings (closed → open, or open after a gap, inside [start, end))
    and the seconds the door stood open within the day. `points` are in
    time order and may begin before `start`."""
    openings = 0
    open_seconds = 0.0
    was_open: bool | None = None  # None: unknown (before the first reading or after a gap)
    for i, (t, v) in enumerate(points):
        is_open = v >= 0.5
        nxt = points[i + 1][0] if i + 1 < len(points) else end
        if was_open is not None and i > 0 and t - points[i - 1][0] > MAX_GAP:
            was_open = None
        if is_open and was_open is not True and start <= t < end:
            openings += 1
        if is_open:
            a = max(t, start)
            b = min(nxt, t + MAX_GAP, end)
            if b > a:
                open_seconds += (b - a).total_seconds()
        was_open = is_open
    return DoorDay(openings, round(open_seconds))
