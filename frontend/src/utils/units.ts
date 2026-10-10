/**
 * Formatting of sensor readings in the sensor's own unit.
 *
 * The backend sends `unit` with every sensor ("°C", "A", "V", "W", "kWh");
 * sensors from before units existed have none and are temperatures.
 */

const DECIMALS: Record<string, number> = { "°C": 1, A: 2, V: 1, W: 0, kWh: 2 };

export function unitOf(sensor: { unit?: string | null } | null | undefined): string {
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
    default:
      return high ? "HIGH TEMP" : "LOW TEMP";
  }
}
