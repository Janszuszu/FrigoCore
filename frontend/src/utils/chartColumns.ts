// Shared between the sensors store (an initial estimate, made before the
// chart has mounted and measured itself) and TemperatureChart (the real,
// measured value) so both sides agree on the same width -> column-count
// mapping and the store's first fetch is already close to correct.
//
// A fixed ~9px pitch per column keeps every column comfortably wide enough
// to read at any screen size; the min/max clamp keeps both extremes sane —
// a narrow phone never asks for fewer than 40 columns, and a wide desktop
// chart never asks for more than 100 (a calmer upper bound, not one column
// per pixel).
const MIN_COLUMN_PITCH_PX = 9;
const MIN_TARGET_COLUMNS = 40;
const MAX_TARGET_COLUMNS = 100;

export function targetColumnsForWidth(widthPx: number): number {
  if (!widthPx || widthPx <= 0) return MIN_TARGET_COLUMNS;
  const raw = Math.round(widthPx / MIN_COLUMN_PITCH_PX);
  return Math.min(MAX_TARGET_COLUMNS, Math.max(MIN_TARGET_COLUMNS, raw));
}
