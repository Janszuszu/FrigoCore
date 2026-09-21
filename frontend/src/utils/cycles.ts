export interface CycleStats {
  count: number;
  avgMs: number | null;
}

// Minimum swing (°C) for a reversal to count as a real min/max, so sensor
// noise around a plateau is not mistaken for a work cycle.
export const CYCLE_MIN_SWING_C = 1;

/**
 * One work cycle = min -> max -> min. Extremes are confirmed with a
 * zig-zag filter: a turning point only counts once the temperature has
 * moved at least `swing` away from it in the opposite direction.
 */
export function countCycles(
  points: { t: number; temp: number }[],
  swing: number = CYCLE_MIN_SWING_C,
): CycleStats {
  const extremes: { t: number; kind: "min" | "max" }[] = [];
  if (points.length < 3) return { count: 0, avgMs: null };

  let dir: "up" | "down" | null = null;
  let cand = points[0];
  for (let i = 1; i < points.length; i++) {
    const p = points[i];
    if (dir === null) {
      if (p.temp - cand.temp >= swing) {
        extremes.push({ t: cand.t, kind: "min" });
        dir = "up";
        cand = p;
      } else if (cand.temp - p.temp >= swing) {
        extremes.push({ t: cand.t, kind: "max" });
        dir = "down";
        cand = p;
      }
    } else if (dir === "up") {
      if (p.temp > cand.temp) cand = p;
      else if (cand.temp - p.temp >= swing) {
        extremes.push({ t: cand.t, kind: "max" });
        dir = "down";
        cand = p;
      }
    } else {
      if (p.temp < cand.temp) cand = p;
      else if (p.temp - cand.temp >= swing) {
        extremes.push({ t: cand.t, kind: "min" });
        dir = "up";
        cand = p;
      }
    }
  }

  // The trailing candidate already swung `swing` away from the previous
  // extreme, so it is a real turning point even if not yet reversed.
  if (dir) extremes.push({ t: cand.t, kind: dir === "up" ? "max" : "min" });

  // Confirmed cycles: every min, max, min triple.
  const durations: number[] = [];
  for (let i = 0; i + 2 < extremes.length; i++) {
    if (extremes[i].kind === "min" && extremes[i + 1].kind === "max" && extremes[i + 2].kind === "min") {
      durations.push(extremes[i + 2].t - extremes[i].t);
    }
  }
  const count = durations.length;
  return { count, avgMs: count ? durations.reduce((a, b) => a + b, 0) / count : null };
}
