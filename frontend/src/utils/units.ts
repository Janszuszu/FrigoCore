/**
 * Formatting of sensor readings in the sensor's own unit.
 *
 * The backend sends `unit` with every sensor ("°C", "A", "V", "W", "kWh");
 * sensors from before units existed have none and are temperatures.
 * On/off sensors (door, defrost) have no unit: their 0/1 reading is shown
 * as a word instead.
 */

const STATE_LABELS: Record<string, [string, string]> = {
  door: ["Zamknięte", "Otwarte"],
  defrost: ["Chłodzenie", "Odszranianie"],
};

export function isStateKind(kind: string | null | undefined): boolean {
  return !!kind && kind in STATE_LABELS;
}

/** "Otwarte" / "Zamknięte" etc. for a 0/1 reading of an on/off sensor. */
export function stateLabel(value: number | null | undefined, kind: string): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return STATE_LABELS[kind][value >= 0.5 ? 1 : 0];
}

/** A sensor's reading as shown to people — a word for on/off sensors,
 * the number with its unit otherwise. */
export function formatSensorValue(
  value: number | null | undefined,
  sensor: { unit?: string | null; kind?: string | null } | null | undefined,
): string {
  if (sensor && isStateKind(sensor.kind)) return stateLabel(value, sensor.kind as string);
  return formatReading(value, unitOf(sensor));
}

const DECIMALS: Record<string, number> = { "°C": 1, A: 2, V: 1, W: 0, kWh: 2 };

export function unitOf(sensor: { unit?: string | null; kind?: string | null } | null | undefined): string {
  if (isStateKind(sensor?.kind)) return "";
  return sensor?.unit || "°C";
}

/** Number only, rounded for the unit — e.g. "241.3", "0.35". */
export function formatNumber(value: number | null | undefined, unit: string): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(DECIMALS[unit] ?? 1);
}

/** Number with its unit — e.g. "241.3 V". */
export function formatReading(value: number | null | undefined, unit: string): string {
  const number = formatNumber(value, unit);
  return number === "—" ? number : `${number} ${unit}`;
}

/** Short alarm label for a sensor card, worded for what the sensor measures. */
export function alarmShortLabel(alarmType: string, kind: string | undefined): string {
  if (alarmType === "offline") return "OFFLINE";
  const high = alarmType === "high_temperature";
  switch (kind) {
    case "current":
      return high ? "PRZECIĄŻENIE" : "NISKI PRĄD";
    case "voltage":
      return high ? "WYSOKIE NAPIĘCIE" : "NISKIE NAPIĘCIE";
    case "power":
      return high ? "WYSOKA MOC" : "NISKA MOC";
    case "energy":
      return high ? "WYSOKIE ZUŻYCIE" : "NISKIE ZUŻYCIE";
    case "door":
      return high ? "DRZWI OTWARTE" : "DRZWI ZAMKNIĘTE";
    case "defrost":
      return high ? "ODSZRANIANIE" : "BRAK ODSZRANIANIA";
    default:
      return high ? "HIGH TEMP" : "LOW TEMP";
  }
}
