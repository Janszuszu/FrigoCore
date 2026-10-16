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
    # 0/1 states read from a controller's status bits (1 = open / defrosting).
    DOOR = "door"
    DEFROST = "defrost"


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
    # (label for 0, label for 1) for on/off sensors; None for measurements.
    # A state alarm has no value worth reading out, only its reason.
    states: tuple[str, str] | None = None


SENSOR_KINDS: dict[SensorKind, SensorKindInfo] = {
    SensorKind.TEMPERATURE: SensorKindInfo("°C", "Wysoka temperatura", "Niska temperatura", "stopni"),
    SensorKind.CURRENT: SensorKindInfo("A", "Przeciążenie — wysoki prąd", "Niski prąd", "ampera"),
    SensorKind.VOLTAGE: SensorKindInfo("V", "Wysokie napięcie", "Niskie napięcie", "woltów"),
    SensorKind.POWER: SensorKindInfo("W", "Wysoka moc", "Niska moc", "watów"),
    SensorKind.ENERGY: SensorKindInfo(
        "kWh", "Wysokie zużycie energii", "Niskie zużycie energii", "kilowatogodzin", cumulative=True
    ),
    # A door alarm is a HIGH alarm with a threshold of 0.5 — the trigger
    # delay is how long the door may stay open.
    SensorKind.DOOR: SensorKindInfo(
        "", "Drzwi otwarte", "Drzwi zamknięte", "", states=("Zamknięte", "Otwarte")
    ),
    SensorKind.DEFROST: SensorKindInfo(
        "", "Odszranianie trwa", "Brak odszraniania", "", states=("Chłodzenie", "Odszranianie")
    ),
}

# Defrost sensor slug suffix. A defrost sensor whose topic ends in
# "<group>-odszranianie" covers the temperature sensors of its object whose
# topic ends in "<group>" or "<group>-..." (e.g. "komora", "komora-parownik"):
# their high-temperature alarms wait while the defrost is on.
DEFROST_TOPIC_SUFFIX = "-odszranianie"

SENSOR_KIND_PATTERN = "^(" + "|".join(k.value for k in SensorKind) + ")$"


def kind_info(kind: str | SensorKind | None) -> SensorKindInfo:
    """Info for a stored kind; anything unknown falls back to temperature,
    the only kind that existed before kinds were introduced."""
    try:
        return SENSOR_KINDS[SensorKind(kind)]
    except ValueError:
        return SENSOR_KINDS[SensorKind.TEMPERATURE]
