"""FrigoCore — what a sensor measures.

Every sensor carries a `kind`. The kind decides the unit shown next to its
readings and the wording of its alarms (dashboard, push and voice call).
Readings of every kind share the same storage — `Measurement.temperature`
and `Sensor.current_temperature` predate this module and keep their names so
existing clients keep working; for a non-temperature sensor they simply hold
that sensor's value in its own unit.
"""

from dataclasses import dataclass
from enum import Enum


class SensorKind(str, Enum):
    TEMPERATURE = "temperature"
    CURRENT = "current"
    VOLTAGE = "voltage"
    POWER = "power"
    ENERGY = "energy"


@dataclass(frozen=True, slots=True)
class SensorKindInfo:
    unit: str
    # Polish alarm causes, e.g. "Przeciążenie — wysoki prąd".
    high_reason: str
    low_reason: str
    # Unit as read aloud by the voice call ("12,4 ampera").
    spoken_unit: str
    # True for counters that only ever grow (kWh): the chart and the daily
    # summary show consumption, not the raw counter value.
    cumulative: bool = False


SENSOR_KINDS: dict[SensorKind, SensorKindInfo] = {
    SensorKind.TEMPERATURE: SensorKindInfo("°C", "Wysoka temperatura", "Niska temperatura", "stopni"),
    SensorKind.CURRENT: SensorKindInfo("A", "Przeciążenie — wysoki prąd", "Niski prąd", "ampera"),
    SensorKind.VOLTAGE: SensorKindInfo("V", "Wysokie napięcie", "Niskie napięcie", "woltów"),
    SensorKind.POWER: SensorKindInfo("W", "Wysoka moc", "Niska moc", "watów"),
    SensorKind.ENERGY: SensorKindInfo(
        "kWh", "Wysokie zużycie energii", "Niskie zużycie energii", "kilowatogodzin", cumulative=True
    ),
}

SENSOR_KIND_PATTERN = "^(" + "|".join(k.value for k in SensorKind) + ")$"


def kind_info(kind: str | SensorKind | None) -> SensorKindInfo:
    """Info for a stored kind; anything unknown falls back to temperature,
    the only kind that existed before kinds were introduced."""
    try:
        return SENSOR_KINDS[SensorKind(kind)]
    except ValueError:
        return SENSOR_KINDS[SensorKind.TEMPERATURE]
