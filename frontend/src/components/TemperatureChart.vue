<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { AlarmItem, ChartRange, MeasurementItem, SensorItem } from '@/types'

const props = defineProps<{
  sensor: SensorItem
  readings: MeasurementItem[] // ascending by received_at (oldest first)
  range: ChartRange
  highThreshold: number | null
  lowThreshold: number | null
  alarms: AlarmItem[] // this sensor's alarms overlapping the visible range
  activeAlarmLabel: string | null
  online: boolean
  loading: boolean
}>()

const isLive = computed(() => props.range === 'LIVE')

// ─── Layout constants (internal SVG coordinate space) ──────────────
// No Y-axis scale and no separate alarm-marker row anymore — the exact
// value is a tap away (point tooltip), and an alarm is opened by tapping
// the alarm-colored column itself (see tryAlarmPopupFromHover), not a
// dedicated strip below the chart. The bottom margin only needs to fit
// one row of periodic time labels; the left margin is just edge padding.
const VB_W = 1000
const VB_H = 340
const MARGIN = { top: 16, right: 16, bottom: 36, left: 16 }
const PLOT_W = VB_W - MARGIN.left - MARGIN.right
const PLOT_H = VB_H - MARGIN.top - MARGIN.bottom
const XLABEL_Y = MARGIN.top + PLOT_H + 24

// ─── Data ────────────────────────────────────────────────────────
const validReadings = computed(() =>
  props.readings.filter(
    (r): r is MeasurementItem & { temperature: number } =>
      typeof r.temperature === 'number' && !Number.isNaN(r.temperature),
  ),
)

// ─── Zoom / pan window (fractions of validReadings, 0..1) ─────────
// Disabled entirely while LIVE (oscilloscope mode has no zoom/pan concept).
const zoomStart = ref(0)
const zoomEnd = ref(1)

const visible = computed(() => {
  const d = validReadings.value
  if (d.length < 2) return d
  const startIdx = Math.floor(zoomStart.value * (d.length - 1))
  const endIdx = Math.ceil(zoomEnd.value * (d.length - 1))
  return d.slice(startIdx, Math.max(endIdx + 1, startIdx + 2))
})

const isZoomed = computed(() => zoomStart.value > 0.001 || zoomEnd.value < 0.999)

// Fullscreen is owned by the parent (DashboardView) now, since the range
// selector must stay visible in fullscreen too — it needs to wrap more
// than just this component. rootEl here is only used to detect "tapped
// outside this chart" for closing a locked touch selection. Zoom/pan
// state (zoomStart/zoomEnd) is unaffected either way.
const rootEl = ref<HTMLElement | null>(null)

// ─── Y domain: nice, padded, includes thresholds so they're visible ─
function niceStep(rawStep: number): number {
  if (rawStep <= 0) return 1
  const mag = 10 ** Math.floor(Math.log10(rawStep))
  const norm = rawStep / mag
  const niceNorm = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10
  return niceNorm * mag
}

const yDomain = computed(() => {
  const temps = visible.value.map((r) => r.temperature)
  const extra: number[] = []
  if (props.highThreshold != null) extra.push(props.highThreshold)
  if (props.lowThreshold != null) extra.push(props.lowThreshold)
  const all = temps.length ? temps.concat(extra) : extra.length ? extra : [0, 1]
  const rawMin = Math.min(...all)
  const rawMax = Math.max(...all)
  const span = rawMax - rawMin || 1
  const pad = Math.max(span * 0.18, 1)
  const paddedMin = rawMin - pad
  const paddedMax = rawMax + pad
  const step = niceStep((paddedMax - paddedMin) / 5)
  const min = Math.floor(paddedMin / step) * step
  const max = Math.ceil(paddedMax / step) * step
  return { min, max, step }
})

// Y-axis ticks always include the exact HIGH/LOW threshold values (not
// just "nice round" step ticks) — per the SCADA-style requirement that
// alarm boundaries be obvious from the axis itself, with no on-chart
// text. If a threshold lands close to a regular tick already, it just
// marks that tick instead of adding a crowded near-duplicate.
interface YTick {
  value: number
  isHigh: boolean
  isLow: boolean
}

function buildYTicks(min: number, max: number, step: number, lowT: number | null, highT: number | null): YTick[] {
  const ticks: YTick[] = []
  for (let v = min; v <= max + step * 0.001; v += step) {
    ticks.push({ value: Math.round(v * 100) / 100, isHigh: false, isLow: false })
  }
  function markOrAdd(temp: number, mark: 'isHigh' | 'isLow') {
    const rounded = Math.round(temp * 100) / 100
    const existing = ticks.find((t) => Math.abs(t.value - rounded) < step * 0.25)
    if (existing) {
      existing[mark] = true
      existing.value = rounded // show the precise threshold, not the nearby "nice" number
    } else if (rounded >= min && rounded <= max) {
      ticks.push({ value: rounded, isHigh: mark === 'isHigh', isLow: mark === 'isLow' })
    }
  }
  if (highT != null) markOrAdd(highT, 'isHigh')
  if (lowT != null) markOrAdd(lowT, 'isLow')
  return ticks.sort((a, b) => a.value - b.value)
}

const yTicks = computed(() => {
  const { min, max, step } = yDomain.value
  return buildYTicks(min, max, step, props.lowThreshold, props.highThreshold)
})

function yScale(temp: number): number {
  const { min, max } = yDomain.value
  const span = max - min || 1
  return MARGIN.top + PLOT_H - ((temp - min) / span) * PLOT_H
}

// ─── X domain: time-based, mapped across the visible slice ────────
const xDomain = computed(() => {
  const d = visible.value
  if (!d.length) return { start: 0, end: 1 }
  const start = new Date(d[0].received_at).getTime()
  const end = new Date(d[d.length - 1].received_at).getTime()
  return { start, end: end > start ? end : start + 1 }
})

function xScale(isoTime: string): number {
  const t = new Date(isoTime).getTime()
  const { start, end } = xDomain.value
  return MARGIN.left + ((t - start) / (end - start)) * PLOT_W
}

function xScaleMs(t: number): number {
  const { start, end } = xDomain.value
  const clamped = Math.min(Math.max(t, start), end)
  return MARGIN.left + ((clamped - start) / (end - start)) * PLOT_W
}

// ─── Responsive tick count — driven by the chart's actual rendered
// width (via ResizeObserver on rootEl), not the window's width. A chart
// that isn't full-viewport-width (embedded, split layout, etc.) gets the
// right tick count for ITS OWN space, and label count never exceeds what
// the available pixels can actually hold without touching. ───────────
const containerWidthPx = ref(390)
const containerHeightPx = ref(300)
let containerResizeObserver: ResizeObserver | null = null

// Rough per-format label width (real px) — wide enough that adjacent
// labels never touch even at the larger mobile font-size.
const minLabelWidthPx = computed(() => {
  if (props.range === 'LIVE') return 66 // "HH:mm:ss"
  if (props.range === '7D') return 86 // "dd.MM HH:mm"
  return 52 // "HH:mm" (1H/24H, and the short auto-fallback)
})

const tickCount = computed(() => {
  const plotWidthPx = containerWidthPx.value * (PLOT_W / VB_W)
  // The first/last labels are edge-anchored (start/end) so their full
  // width extends inward from the axis edge, unlike interior labels which
  // are center-anchored and only need half their width on each side. The
  // binding constraint is therefore the edge-to-neighbor gap, which needs
  // ~1.5x a label's width to clear — not 1x, or the outermost ticks
  // collide with their neighbor at narrow/mobile widths.
  const maxTicks = Math.floor(plotWidthPx / (minLabelWidthPx.value * 1.5))
  // Capped at 6, not 7 — a calmer, less busy vertical grid on wide desktop
  // screens without losing resolution anywhere narrower (the width-driven
  // formula above is still what actually binds on mobile/tablet).
  return Math.min(6, Math.max(2, maxTicks))
})

const xTicks = computed(() => {
  const { start, end } = xDomain.value
  const count = tickCount.value
  const spanMs = end - start
  const ticks: { x: number; label: string }[] = []
  for (let i = 0; i <= count; i++) {
    const t = start + (spanMs * i) / count
    ticks.push({ x: xScaleMs(t), label: formatAxisTime(t, spanMs) })
  }
  return ticks
})

// Labels are keyed to the explicitly selected range first (LIVE clock time,
// 1H/24H time-of-day, 7D date+time) since that's what the user is
// deliberately asking to see regardless of how much data is actually
// loaded. Any range this component doesn't know about yet (or a zoomed
// slice) falls back to a span-based auto choice so it's never wrong:
// minutes/hours -> time, days -> date+time, months -> month + day. A
// chart spanning more than a day never shows hour-only labels.
const MINUTE_MS = 60 * 1000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

function formatDateAndHour(d: Date): string {
  const datePart = d.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })
  const timePart = d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })
  return `${datePart} ${timePart}`
}

function formatAxisTime(ms: number, spanMs: number): string {
  const d = new Date(ms)
  if (props.range === 'LIVE') {
    return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }
  if (props.range === '1H' || props.range === '24H') {
    return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })
  }
  if (props.range === '7D') {
    return formatDateAndHour(d)
  }
  // Auto fallback (e.g. a zoomed-in slice, or a future range) — never
  // show hour-only labels once the span crosses a day.
  if (spanMs <= DAY_MS) return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })
  if (spanMs <= 90 * DAY_MS) return formatDateAndHour(d)
  return d.toLocaleDateString('pl-PL', { day: '2-digit', month: 'short' })
}

// ─── Render-point decimation ────────────────────────────────────────
// Keeps the rendered column count tractable with 10k+ historical points
// without touching the domain/tooltip/marker logic, which still use the
// full-fidelity `visible` array. Min/max-per-bucket by temperature (not a
// stride/average) so real excursions above/below a threshold are never
// decimated away.
const RENDER_POINT_BUDGET = 2000

function decimateForRender<T extends { x: number; t: number }>(points: T[], maxPoints: number): T[] {
  if (points.length <= maxPoints) return points
  const bucketSize = Math.ceil(points.length / (maxPoints / 2))
  const result: T[] = []
  for (let i = 0; i < points.length; i += bucketSize) {
    const bucket = points.slice(i, i + bucketSize)
    if (!bucket.length) continue
    let minP = bucket[0]
    let maxP = bucket[0]
    for (const p of bucket) {
      if (p.t < minP.t) minP = p
      if (p.t > maxP.t) maxP = p
    }
    if (minP === maxP) {
      result.push(minP)
    } else if (minP.x <= maxP.x) {
      result.push(minP, maxP)
    } else {
      result.push(maxP, minP)
    }
  }
  return result
}

// ─── Threshold-anchored color story ────────────────────────────────
// Exactly three colors, no blend, no gradient: green in the normal
// range, red above HIGH, blue below LOW. Each column is a single solid
// fill, decided from that column's own measurement only.
const COLUMN_COLOR_LOW = '#3b82f6'
const COLUMN_COLOR_NORMAL = '#22c55e'
const COLUMN_COLOR_HIGH = '#ef4444'

interface Column {
  x: number
  y: number
  width: number
  height: number
  color: string
}

// ─── True baseline column chart (ECMWF-anomaly style) ─────────────────
// This is NOT a line chart redrawn as rectangles — there is no path, no
// bridging, no per-neighbor sizing, nothing derived from the shape of a
// curve. Every column is independent, identical width, constant spacing,
// rooted at a fixed reference temperature (0°C) rather than the bottom of
// the plot. That's the part that actually matters: because the baseline
// sits inside the domain instead of at its floor, a column grows UP from
// it for a reading >= 0°C and DOWN from it for a reading < 0°C — exactly
// like an ECMWF anomaly bar grows up for a positive anomaly and down for
// a negative one. Rooting every column at the plot's bottom edge instead
// (an earlier attempt) traces the exact same silhouette as the old line
// chart, just filled in solid — which is why it still read as "a line
// wearing rectangles" even once the rectangles themselves were correct.
//
// A missing sample is simply a missing column — width/spacing come from
// `PLOT_W / column count`, never from the calendar time to a neighbor, so
// a sensor's offline gap can't stretch or balloon the columns next to it.
const BASELINE_TEMP = 0
const COLUMN_GAP_FRACTION = 0.32
const MIN_COLUMN_WIDTH = 0.6
const MIN_COLUMN_HEIGHT = 1.5

function buildColumns(
  points: { x: number; t: number }[],
  scaleFn: (temp: number) => number,
  lowT: number | null,
  highT: number | null,
  plotTop: number,
  plotBottom: number,
): Column[] {
  if (!points.length) return []
  const pitch = points.length > 1 ? PLOT_W / points.length : PLOT_W
  const width = Math.max(pitch * (1 - COLUMN_GAP_FRACTION), MIN_COLUMN_WIDTH)
  // Clamped into the visible plot so a baseline temperature outside the
  // current domain (a sensor that never gets near 0°C) still produces a
  // sane one-directional column chart instead of one shooting past the edge.
  const baselineY = Math.min(Math.max(scaleFn(BASELINE_TEMP), plotTop), plotBottom)
  return points.map((p) => {
    const py = scaleFn(p.t)
    const top = Math.min(py, baselineY)
    const height = Math.max(Math.abs(py - baselineY), MIN_COLUMN_HEIGHT)
    const color = highT != null && p.t > highT ? COLUMN_COLOR_HIGH : lowT != null && p.t < lowT ? COLUMN_COLOR_LOW : COLUMN_COLOR_NORMAL
    return { x: p.x - width / 2, y: top, width, height, color }
  })
}

const columns = computed<Column[]>(() => {
  const d = visible.value
  if (!d.length) return []
  const points = d.map((r) => ({ x: xScale(r.received_at), t: r.temperature }))
  const decimated = decimateForRender(points, RENDER_POINT_BUDGET)
  return buildColumns(decimated, yScale, props.lowThreshold, props.highThreshold, MARGIN.top, MARGIN.top + PLOT_H)
})

// ─── LIVE mode: oscilloscope-style sweep ──────────────────────────
// Independent of the historical zoom/pan/columns machinery above. The
// x-axis is real wall-clock time anchored at when LIVE (re)started, not a
// normalized 0..1 window over a fetched dataset. `liveNow` is driven by
// requestAnimationFrame — a genuine 30-60fps sweep, not a fixed-interval
// tick — so the trace glides continuously between arrivals instead of
// stepping. New points only ever get pushed onto `livePoints` (never a
// data refetch); the smoothed path recomputes from that small, bounded,
// in-memory buffer, which costs nothing at LIVE's actual data rate.
const LIVE_WINDOW_MS = 5 * 60 * 1000 // visible sweep width once filled

const livePoints = ref<{ t: number; temp: number }[]>([])
const liveSweepStart = ref(Date.now())
const liveNow = ref(Date.now())
const LIVE_PX_PER_MS = PLOT_W / LIVE_WINDOW_MS
let liveRafId: number | null = null

function liveFrame() {
  liveNow.value = Date.now()
  liveRafId = requestAnimationFrame(liveFrame)
}
function startLiveClock() {
  stopLiveClock()
  liveRafId = requestAnimationFrame(liveFrame)
}
function stopLiveClock() {
  if (liveRafId != null) {
    cancelAnimationFrame(liveRafId)
    liveRafId = null
  }
}

function liveRawX(t: number): number {
  return MARGIN.left + (t - liveSweepStart.value) * LIVE_PX_PER_MS
}

const liveYDomain = computed(() => {
  const temps = livePoints.value.map((p) => p.temp)
  const extra: number[] = []
  if (props.highThreshold != null) extra.push(props.highThreshold)
  if (props.lowThreshold != null) extra.push(props.lowThreshold)
  const all = temps.length ? temps.concat(extra) : extra.length ? extra : [0, 1]
  const rawMin = Math.min(...all)
  const rawMax = Math.max(...all)
  const span = rawMax - rawMin || 1
  const pad = Math.max(span * 0.18, 1)
  const paddedMin = rawMin - pad
  const paddedMax = rawMax + pad
  const step = niceStep((paddedMax - paddedMin) / 5)
  const min = Math.floor(paddedMin / step) * step
  const max = Math.ceil(paddedMax / step) * step
  return { min, max, step }
})

const liveYTicks = computed(() => {
  const { min, max, step } = liveYDomain.value
  return buildYTicks(min, max, step, props.lowThreshold, props.highThreshold)
})

function liveYScale(temp: number): number {
  const { min, max } = liveYDomain.value
  const span = max - min || 1
  return MARGIN.top + PLOT_H - ((temp - min) / span) * PLOT_H
}

// Recomputed only when livePoints/thresholds actually change (i.e. on a
// real new measurement) — NOT on the 60fps `liveNow` tick, which only
// drives the cheap shift transform below.
const liveColumns = computed<Column[]>(() => {
  const points = livePoints.value.map((p) => ({ x: liveRawX(p.t), t: p.temp }))
  return buildColumns(points, liveYScale, props.lowThreshold, props.highThreshold, MARGIN.top, MARGIN.top + PLOT_H)
})

// The last timestamp actually appended to livePoints — the ONLY reliable
// way to know "did new data arrive". The store's live measurement array
// is a length-capped ring buffer (unshift + pop at LIVE_CAP), so once a
// long-running LIVE session fills it, its .length stops changing on every
// subsequent WS push even though genuinely new points keep arriving (an
// old one is evicted for each new one). Comparing array lengths was the
// previous (broken) approach — it misread "length didn't grow" as "no new
// data / snapshot changed", forcing a full resetLive() on every single
// live measurement once the cap was reached, which is what caused the
// sweep to keep flickering/restarting instead of extending smoothly.
let lastAppendedLiveTs: number | null = null

function resetLive() {
  livePoints.value = []
  liveSweepStart.value = Date.now()
  liveNow.value = liveSweepStart.value
  lastAppendedLiveTs = null
}

function appendLivePoint(t: number, temp: number) {
  livePoints.value.push({ t, temp })
  const cutoff = t - LIVE_WINDOW_MS * 1.5
  while (livePoints.value.length > 1 && livePoints.value[0].t < cutoff) livePoints.value.shift()
}

// The sweep: before the window is filled, the head simply advances from
// the left edge (shift stays 0, satisfying "start drawing from the left
// edge"); once the head passes the right edge, everything shifts left by
// the overflow amount so the newest point stays pinned at the edge.
const liveShiftPx = computed(() => {
  const rightEdge = MARGIN.left + PLOT_W
  const headX = liveRawX(liveNow.value)
  return headX > rightEdge ? rightEdge - headX : 0
})

// Tick x-positions track liveNow every frame for a smooth slide; the
// (relatively expensive) Intl label text only needs to change once a
// second, so each tick index memoizes its own last-formatted second —
// avoiding ~60 redundant Intl.DateTimeFormat calls/sec per tick.
const liveTickLabelCache: { second: number; label: string }[] = []
function liveTickLabel(index: number, ms: number): string {
  const second = Math.floor(ms / 1000)
  const cached = liveTickLabelCache[index]
  if (cached && cached.second === second) return cached.label
  const label = formatAxisTime(second * 1000, LIVE_WINDOW_MS)
  liveTickLabelCache[index] = { second, label }
  return label
}

const liveXTicks = computed(() => {
  const count = tickCount.value
  // Clamp to the actual sweep start — right after LIVE (re)starts, a full
  // LIVE_WINDOW_MS hasn't elapsed yet, so `liveNow - LIVE_WINDOW_MS` would
  // be a time BEFORE the sweep began, producing ticks anchored at
  // negative/off-screen positions. Ticks compress toward "now" during the
  // fill-up phase and reach their normal full spacing once the window
  // genuinely fills — same idea as the sweep itself starting empty.
  const windowStart = Math.max(liveSweepStart.value, liveNow.value - LIVE_WINDOW_MS)
  const windowSpan = liveNow.value - windowStart || 1
  const ticks: { x: number; label: string }[] = []
  for (let i = 0; i <= count; i++) {
    const t = windowStart + (windowSpan * i) / count
    ticks.push({ x: liveRawX(t) + liveShiftPx.value, label: liveTickLabel(i, t) })
  }
  return ticks
})

watch(isLive, (live) => {
  if (live) {
    resetLive()
    startLiveClock()
  } else {
    stopLiveClock()
  }
}, { immediate: true })

// Unified readings watcher: LIVE mode appends only genuinely new points
// (no zoom/selection to reset — both are disabled in LIVE); historical
// ranges keep the full-reset behavior when the parent swaps in a new
// snapshot.
//
// "New" is decided by timestamp against lastAppendedLiveTs, NOT by array
// length. The store's live buffer is a capped ring (see LIVE_CAP in
// stores/sensors.ts) — its length plateaus once full even though the
// WS is still delivering fresh measurements, so length-diffing can't
// distinguish "nothing new happened" from "the buffer is just full".
// Timestamp identity has no such blind spot: it's correct whether the
// array grew, stayed the same length, or (in principle) shrank.
watch(
  () => props.readings,
  (newR) => {
    if (!isLive.value) {
      zoomStart.value = 0
      zoomEnd.value = 1
      clearSelection()
      return
    }
    if (newR.length === 0) {
      resetLive()
      return
    }
    for (const r of newR) {
      if (typeof r.temperature !== 'number' || Number.isNaN(r.temperature)) continue
      const t = new Date(r.received_at).getTime()
      if (lastAppendedLiveTs != null && t <= lastAppendedLiveTs) continue
      appendLivePoint(t, r.temperature)
      lastAppendedLiveTs = t
    }
  },
)


// ─── Alarm periods — the chart itself is the interaction surface now ──
// There is no separate marker strip anymore: an alarm popup opens by
// tapping/clicking the red or blue column that belongs to it, directly on
// the plot (see tryAlarmPopupFromHover). This just indexes each alarm's
// [start, end] time window (and the min/max reached during it) so a
// clicked column's reading can be matched back to the alarm it belongs to.
const ALARM_CLASS: Record<string, string> = {
  high_temperature: 'marker-high',
  low_temperature: 'marker-low',
  offline: 'marker-offline',
}

const alarmPeriods = computed(() => {
  return props.alarms
    .filter((alarm) => alarm.alarm_type === 'high_temperature' || alarm.alarm_type === 'low_temperature')
    .map((alarm) => {
      const startMs = new Date(alarm.triggered_at ?? alarm.detected_at).getTime()
      const endMs = alarm.resolved_at ? new Date(alarm.resolved_at).getTime() : Date.now()
      const inWindow = validReadings.value.filter((r) => {
        const t = new Date(r.received_at).getTime()
        return t >= startMs && t <= endMs
      })
      const temps = inWindow.map((r) => r.temperature)
      return {
        alarm,
        startMs,
        endMs,
        cls: ALARM_CLASS[alarm.alarm_type] ?? 'marker-offline',
        maxTemp: temps.length ? Math.max(...temps) : null,
        minTemp: temps.length ? Math.min(...temps) : null,
      }
    })
})

// Given a clicked/tapped reading, decides which alarm (if any) it belongs
// to — by re-deriving HIGH/LOW from the reading's own temperature against
// the thresholds (the exact same rule buildColumns uses to color that
// column), then finding the alarm period of that type whose window
// contains the reading's timestamp. A green column never matches anything.
function findAlarmForReading(reading: MeasurementItem & { temperature: number }) {
  const isHigh = props.highThreshold != null && reading.temperature > props.highThreshold
  const isLow = props.lowThreshold != null && reading.temperature < props.lowThreshold
  if (!isHigh && !isLow) return null
  const wantType = isHigh ? 'high_temperature' : 'low_temperature'
  const t = new Date(reading.received_at).getTime()
  return alarmPeriods.value.find((p) => p.alarm.alarm_type === wantType && t >= p.startMs && t <= p.endMs) ?? null
}

function formatDuration(startIso: string, endIso: string | null): string {
  const startMs = new Date(startIso).getTime()
  const endMs = endIso ? new Date(endIso).getTime() : Date.now()
  const totalMin = Math.max(0, Math.round((endMs - startMs) / 60000))
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function alarmTypeLabel(type: string): string {
  return (
    { high_temperature: 'HIGH TEMPERATURE', low_temperature: 'LOW TEMPERATURE', offline: 'DEVICE OFFLINE' }[
      type
    ] ?? type.toUpperCase()
  )
}

// ─── Hover / crosshair / tooltip ─────────────────────────────────
// hoverIndex is the point currently shown in the tooltip — set either by
// live mouse hover (desktop, transient) or by a touch tap (mobile,
// "locked" until something explicitly clears it: another tap, a tap
// outside the chart, or the chart's data changing).
const svgEl = ref<SVGSVGElement | null>(null)
const hoverIndex = ref<number | null>(null)
const isPointLocked = ref(false)
const hoveredMarker = ref<(typeof alarmPeriods.value)[number] | null>(null)
// Captured at the START of a pointerdown (before hoveredMarker gets
// cleared below), so tryAlarmPopupFromHover can tell "the popup that was
// open when this press began was for THIS SAME alarm" — the only way to
// correctly toggle-close on a second tap of the same column, now that the
// alarm click flows through the chart's own pointer pipeline instead of a
// separate marker element with its own stopPropagation'd handler.
const pointerDownAlarmId = ref<string | null>(null)
const tooltipPos = ref({ x: 0, y: 0 })

function clearSelection() {
  hoverIndex.value = null
  isPointLocked.value = false
}

function svgPoint(clientX: number, clientY: number): { x: number; y: number } | null {
  const el = svgEl.value
  if (!el) return null
  const rect = el.getBoundingClientRect()
  if (!rect.width || !rect.height) return null
  return {
    x: ((clientX - rect.left) / rect.width) * VB_W,
    y: ((clientY - rect.top) / rect.height) * VB_H,
  }
}

function nearestIndex(svgX: number): number | null {
  const d = visible.value
  if (!d.length) return null
  let best = 0
  let bestDist = Infinity
  for (let i = 0; i < d.length; i++) {
    const px = xScale(d[i].received_at)
    const dist = Math.abs(px - svgX)
    if (dist < bestDist) {
      bestDist = dist
      best = i
    }
  }
  return best
}

// ─── Drag to pan (mouse) / tap-to-select then pan (touch) ──────────
// Mouse: unchanged from before — press-drag pans immediately, plain
// hover (no button down) shows the live tooltip.
// Touch: the first contact always selects the nearest point first (per
// spec). Only once the finger moves past PAN_THRESHOLD_PX does the
// gesture turn into a pan — at which point the selection is dropped so
// panning doesn't fight with a stale locked tooltip. A touch that never
// crosses the threshold (a tap, or a long press that merely trembles)
// leaves the point selected and locked.
const PAN_THRESHOLD_PX = 10

const dragging = ref(false)
// Distinct from `dragging` (which just means "mouse button is down since
// this chart started tracking it"): true only once a mousemove actually
// paned the view. A plain click (press+release with no movement in
// between) never sets this, which is exactly what tryAlarmPopupFromHover
// needs to tell "the user clicked a column" apart from "the user dragged
// the chart and happened to release over a column".
const dragMoved = ref(false)
const dragStartX = ref(0)
const dragStartZoom = ref({ start: 0, end: 1 })
const touchOrigin = ref({ x: 0, y: 0 })
const touchIsPanning = ref(false)

function applyPanFraction(dxFraction: number) {
  const windowSize = dragStartZoom.value.end - dragStartZoom.value.start
  let newStart = dragStartZoom.value.start - dxFraction * windowSize
  let newEnd = dragStartZoom.value.end - dxFraction * windowSize
  if (newStart < 0) {
    newEnd -= newStart
    newStart = 0
  }
  if (newEnd > 1) {
    newStart -= newEnd - 1
    newEnd = 1
  }
  zoomStart.value = Math.max(0, newStart)
  zoomEnd.value = Math.min(1, newEnd)
}

function selectAt(pt: { x: number; y: number }, locked: boolean) {
  if (pt.x < MARGIN.left || pt.x > VB_W - MARGIN.right) {
    clearSelection()
    return
  }
  hoverIndex.value = nearestIndex(pt.x)
  isPointLocked.value = locked
  tooltipPos.value = pt
}

// Best-effort: pointer capture can throw (e.g. a pointerId the browser
// doesn't recognize as currently active) and must never block selection
// or panning — those are the behaviors that actually matter here.
function tryCapturePointer(target: EventTarget | null, pointerId: number) {
  try {
    ;(target as Element)?.setPointerCapture?.(pointerId)
  } catch {
    /* not fatal — selection/pan logic runs regardless */
  }
}
function tryReleasePointer(target: EventTarget | null, pointerId: number) {
  try {
    ;(target as Element)?.releasePointerCapture?.(pointerId)
  } catch {
    /* ignore */
  }
}

function onPointerDown(e: PointerEvent) {
  if (isLive.value) return // zoom/pan/selection all disabled while LIVE
  pointerDownAlarmId.value = hoveredMarker.value?.alarm.id ?? null
  hoveredMarker.value = null
  dragStartZoom.value = { start: zoomStart.value, end: zoomEnd.value }
  tryCapturePointer(e.target, e.pointerId)

  if (e.pointerType === 'mouse') {
    dragging.value = true
    dragMoved.value = false
    dragStartX.value = e.clientX
    return
  }

  // Touch / pen: select immediately (tap-first), decide pan-vs-tap on move.
  touchOrigin.value = { x: e.clientX, y: e.clientY }
  touchIsPanning.value = false
  const pt = svgPoint(e.clientX, e.clientY)
  if (pt) selectAt(pt, true)
}

function onPointerMove(e: PointerEvent) {
  if (isLive.value) return
  const pt = svgPoint(e.clientX, e.clientY)
  if (!pt) return

  if (e.pointerType === 'mouse') {
    if (dragging.value) {
      dragMoved.value = true
      hoverIndex.value = null
      const width = svgEl.value?.getBoundingClientRect().width || 1
      applyPanFraction((e.clientX - dragStartX.value) / width)
      return
    }
    selectAt(pt, false)
    return
  }

  // Touch / pen
  if (!touchIsPanning.value) {
    const dist = Math.hypot(e.clientX - touchOrigin.value.x, e.clientY - touchOrigin.value.y)
    if (dist > PAN_THRESHOLD_PX) {
      touchIsPanning.value = true
      clearSelection()
    } else {
      // still within the tap threshold — keep the selection tracking the finger
      selectAt(pt, true)
      return
    }
  }
  const width = svgEl.value?.getBoundingClientRect().width || 1
  applyPanFraction((e.clientX - touchOrigin.value.x) / width)
}

// The chart is the alarm-interaction surface: a plain click (mouse) or a
// tap that never turned into a pan (touch) checks whatever reading is
// currently selected — already computed by selectAt during this same
// press, exactly like the point tooltip — and opens that alarm's popup if
// the reading falls in a HIGH or LOW alarm window. A second tap on the
// same alarm's column toggles it closed again (see pointerDownAlarmId).
function tryAlarmPopupFromHover() {
  if (isLive.value) return // no alarm-column interaction in LIVE (no columns are clicked-selectable there)
  if (hoverIndex.value == null) return
  const reading = visible.value[hoverIndex.value]
  if (!reading || typeof reading.temperature !== 'number') return
  const period = findAlarmForReading(reading as MeasurementItem & { temperature: number })
  if (!period) return
  if (pointerDownAlarmId.value === period.alarm.id) {
    hoveredMarker.value = null
  } else {
    hoveredMarker.value = period
    clearSelection()
  }
}

function onPointerUp(e: PointerEvent) {
  const wasTap = e.pointerType === 'mouse' ? !dragMoved.value : !touchIsPanning.value
  if (wasTap) tryAlarmPopupFromHover()
  dragging.value = false
  touchIsPanning.value = false
  tryReleasePointer(e.target, e.pointerId)
}

function onPointerLeave(e: PointerEvent) {
  if (e.pointerType === 'mouse' && !dragging.value) clearSelection()
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  if (isLive.value) return // zoom disabled while LIVE
  const pt = svgPoint(e.clientX, e.clientY)
  if (!pt) return
  const cursorFraction =
    (pt.x - MARGIN.left) / PLOT_W // 0..1 across the plot area
  const window = zoomEnd.value - zoomStart.value
  const cursorAbs = zoomStart.value + cursorFraction * window
  const zoomFactor = e.deltaY > 0 ? 1.15 : 1 / 1.15
  let newWindow = Math.min(1, Math.max(0.02, window * zoomFactor))
  let newStart = cursorAbs - cursorFraction * newWindow
  let newEnd = newStart + newWindow
  if (newStart < 0) {
    newEnd -= newStart
    newStart = 0
  }
  if (newEnd > 1) {
    newStart -= newEnd - 1
    newEnd = 1
  }
  zoomStart.value = Math.max(0, newStart)
  zoomEnd.value = Math.min(1, newEnd)
}

function resetZoom() {
  zoomStart.value = 0
  zoomEnd.value = 1
}

// ─── Touch: two-finger pinch zoom ──────────────────────────────────
// Single-finger tap/pan is handled entirely by the pointer handlers
// above (Pointer Events unify mouse/touch/pen); this only needs to
// cover the one gesture Pointer Events can't express cleanly — a
// two-finger pinch, which requires reading both active touch points at
// once from the native TouchList.
let touchStartDist = 0
let touchStartZoom = { start: 0, end: 1 }

function touchDist(t: TouchList): number {
  const [a, b] = [t[0], t[1]]
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
}

function onTouchStart(e: TouchEvent) {
  if (isLive.value) return // pinch-zoom disabled while LIVE
  if (e.touches.length === 2) {
    hoveredMarker.value = null
    clearSelection()
    touchStartDist = touchDist(e.touches)
    touchStartZoom = { start: zoomStart.value, end: zoomEnd.value }
  }
}

function onTouchMove(e: TouchEvent) {
  if (isLive.value) return
  if (e.touches.length !== 2) return
  e.preventDefault()
  const dist = touchDist(e.touches)
  if (!touchStartDist) return
  const factor = touchStartDist / dist
  const window = touchStartZoom.end - touchStartZoom.start
  const center = (touchStartZoom.start + touchStartZoom.end) / 2
  let newWindow = Math.min(1, Math.max(0.02, window * factor))
  let newStart = center - newWindow / 2
  let newEnd = center + newWindow / 2
  if (newStart < 0) {
    newEnd -= newStart
    newStart = 0
  }
  if (newEnd > 1) {
    newStart -= newEnd - 1
    newEnd = 1
  }
  zoomStart.value = Math.max(0, newStart)
  zoomEnd.value = Math.min(1, newEnd)
}

// ─── Tooltip content ──────────────────────────────────────────────
const hoveredReading = computed(() => (hoverIndex.value != null ? visible.value[hoverIndex.value] : null))

function fmtTemp(v: number | null | undefined): string {
  return v == null ? '—' : `${v.toFixed(1)} °C`
}
function fmtDate(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleDateString('pl-PL') : '—'
}
function fmtTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleTimeString('pl-PL') : '—'
}

// Converts a point in SVG viewBox units to a CSS position (px) relative to
// the chart container, clamped so the tooltip can never push the layout
// wider than the container (would otherwise cause horizontal overflow on
// narrow viewports).
function positionFromViewBox(vbX: number, vbY: number, boxWidth = 220): { left: string; top: string } {
  const el = svgEl.value
  if (!el) return { left: '0px', top: '0px' }
  const rect = el.getBoundingClientRect()
  const pxPerVbX = rect.width / VB_W
  const pxPerVbY = rect.height / VB_H
  let left = vbX * pxPerVbX + 14
  if (left + boxWidth > rect.width) left = Math.max(0, vbX * pxPerVbX - boxWidth - 14)
  left = Math.min(left, Math.max(0, rect.width - boxWidth))
  const top = Math.max(0, Math.min(vbY * pxPerVbY - 10, rect.height - 140))
  return { left: `${left}px`, top: `${top}px` }
}

// containerWidthPx is read (not used numerically) purely to give this
// computed a reactive dependency on the container's size — without it,
// resizing or rotating the device wouldn't reposition an already-open
// tooltip, since svgEl's bounding rect is read imperatively and isn't
// itself reactive.
const tooltipStyle = computed(() => {
  void containerWidthPx.value
  return positionFromViewBox(tooltipPos.value.x, tooltipPos.value.y)
})

// Tapping a marker's (generous) hit-circle stops the pointerdown from
// reaching the chart's own handler — otherwise the same tap would also
// select/lock the nearest curve point underneath it, showing both popups
// at once. `.stop` on the template binding does that. Tapping the
// already-open alarm's marker again closes its popup (toggle); tapping a
// different marker replaces it, so only one popup ever exists.
// A locked (touch-selected) point tooltip or an open alarm popup only
// close on: another selection (handled in selectAt/tryAlarmPopupFromHover),
// the chart's data changing (handled in the readings watcher), or a tap
// outside the chart entirely — handled here.
function onDocumentPointerDown(e: PointerEvent) {
  if (rootEl.value && rootEl.value.contains(e.target as Node)) return
  if (isPointLocked.value) clearSelection()
  if (hoveredMarker.value) hoveredMarker.value = null
}

// ResizeObserver is the semantically-correct mechanism (also catches a
// layout change that isn't a window resize — a sidebar collapsing, etc.)
// but a plain window 'resize' listener is kept alongside it as a fallback
// measurement, since ResizeObserver has been observed to not fire in at
// least one environment despite the element's own layout genuinely
// having changed. Cheap and harmless to keep both.
function measureContainer() {
  if (!rootEl.value) return
  const rect = rootEl.value.getBoundingClientRect()
  if (rect.width) containerWidthPx.value = rect.width
  if (rect.height) containerHeightPx.value = rect.height
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown, true)
  measureContainer()
  window.addEventListener('resize', measureContainer)
  if (rootEl.value && typeof ResizeObserver !== 'undefined') {
    containerResizeObserver = new ResizeObserver(() => measureContainer())
    containerResizeObserver.observe(rootEl.value)
  }
})
onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown, true)
  window.removeEventListener('resize', measureContainer)
  containerResizeObserver?.disconnect()
  stopLiveClock()
})
</script>

<template>
  <div ref="rootEl" class="temp-chart">
    <div v-if="loading" class="state-message">Ładowanie danych…</div>

    <!-- LIVE: always renders the sweep canvas, even with zero points yet —
         "start drawing from the left edge" means an empty, ready chart,
         not an error/empty state. -->
    <div v-else-if="isLive" class="chart-wrap">
      <svg
        ref="svgEl"
        :viewBox="`0 0 ${VB_W} ${VB_H}`"
        preserveAspectRatio="none"
        class="chart-svg chart-svg-live"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointerleave="onPointerLeave"
        @wheel="onWheel"
        @touchstart="onTouchStart"
        @touchmove="onTouchMove"
      >
        <defs>
          <clipPath id="plot-area-clip">
            <rect :x="MARGIN.left" :y="MARGIN.top" :width="PLOT_W" :height="PLOT_H" />
          </clipPath>
        </defs>

        <!-- Industrial SCADA/HMI look: uniform matte-black background, no
             color fills of any kind behind the graph — just a subtle grid
             and the bar/threshold colors. -->
        <rect x="0" y="0" :width="VB_W" :height="VB_H" class="chart-bg" />

        <!-- Grid stays fixed in place — only the data sweeps. -->
        <line
          v-for="t in liveYTicks"
          :key="`live-grid-${t.value}`"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="liveYScale(t.value)"
          :y2="liveYScale(t.value)"
          class="grid-line"
        />
        <line
          v-for="(tick, i) in liveXTicks"
          :key="`live-vgrid-${i}`"
          :x1="tick.x"
          :x2="tick.x"
          :y1="MARGIN.top"
          :y2="MARGIN.top + PLOT_H"
          class="grid-line"
        />

        <line
          v-if="highThreshold != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="liveYScale(highThreshold)"
          :y2="liveYScale(highThreshold)"
          class="threshold-line threshold-high"
        />
        <line
          v-if="lowThreshold != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="liveYScale(lowThreshold)"
          :y2="liveYScale(lowThreshold)"
          class="threshold-line threshold-low"
        />

        <text
          v-for="(tick, i) in liveXTicks"
          :key="`live-xlabel-${i}`"
          :x="tick.x"
          :y="XLABEL_Y"
          class="axis-label x-label"
          :class="{ 'x-label-first': i === 0, 'x-label-last': i === liveXTicks.length - 1 }"
        >
          {{ tick.label }}
        </text>

        <!-- The sweep itself: clipped to the plot rect and shifted left as
             the window fills, so it visibly scrolls off at the left edge
             like an oscilloscope trace. Each measurement is its own
             baseline-rooted column — liveColumns only recomputes when a
             real point arrives; liveShiftPx (this transform) is the one
             thing driven by the 60fps clock. -->
        <g clip-path="url(#plot-area-clip)">
          <g class="live-sweep" :transform="`translate(${liveShiftPx},0)`">
            <rect
              v-for="(col, i) in liveColumns"
              :key="`live-col-${i}`"
              :x="col.x"
              :y="col.y"
              :width="col.width"
              :height="col.height"
              :fill="col.color"
              class="temp-column"
            />
          </g>
        </g>

      </svg>
    </div>

    <div v-else-if="!validReadings.length" class="empty-state">
      <svg viewBox="0 0 24 24" class="empty-icon"><path d="M3 3v18h18M7 15l3-4 3 3 5-7" /></svg>
      <p class="empty-title">No measurements available</p>
      <p v-if="!online" class="empty-sub offline">Sensor offline</p>
      <p class="empty-sub">
        Last message:
        <strong>{{ sensor.last_message_at ? `${fmtDate(sensor.last_message_at)} ${fmtTime(sensor.last_message_at)}` : 'never' }}</strong>
      </p>
    </div>

    <div v-else-if="validReadings.length < 2" class="state-message">Za mało danych do wykresu</div>

    <div v-else class="chart-wrap">
      <button v-if="isZoomed" type="button" class="reset-zoom" @click="resetZoom">Reset zoom ↺</button>
      <svg
        ref="svgEl"
        :viewBox="`0 0 ${VB_W} ${VB_H}`"
        preserveAspectRatio="none"
        class="chart-svg"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointerleave="onPointerLeave"
        @wheel="onWheel"
        @dblclick="resetZoom"
        @touchstart="onTouchStart"
        @touchmove="onTouchMove"
      >
        <!-- Industrial SCADA/HMI look: uniform matte-black background, no
             color fills of any kind behind the graph — just a subtle grid
             and the bar/threshold colors. -->
        <rect x="0" y="0" :width="VB_W" :height="VB_H" class="chart-bg" />

        <!-- Grid — thin horizontal AND vertical lines, subtle. -->
        <line
          v-for="t in yTicks"
          :key="`grid-${t.value}`"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="yScale(t.value)"
          :y2="yScale(t.value)"
          class="grid-line"
        />
        <line
          v-for="(tick, i) in xTicks"
          :key="`vgrid-${i}`"
          :x1="tick.x"
          :x2="tick.x"
          :y1="MARGIN.top"
          :y2="MARGIN.top + PLOT_H"
          class="grid-line"
        />

        <!-- Threshold lines (visually distinct from grid: dashed + color).
             The dashed lines and the line's own color transitions are the
             only alarm indicators — no zone shading, no area fill. -->
        <line
          v-if="highThreshold != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="yScale(highThreshold)"
          :y2="yScale(highThreshold)"
          class="threshold-line threshold-high"
        />
        <line
          v-if="lowThreshold != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="yScale(lowThreshold)"
          :y2="yScale(lowThreshold)"
          class="threshold-line threshold-low"
        />

        <!-- X axis labels — first/last are anchored inward (not centered)
             so they never overhang past the plot edge. -->
        <text
          v-for="(tick, i) in xTicks"
          :key="`xlabel-${i}`"
          :x="tick.x"
          :y="XLABEL_Y"
          class="axis-label x-label"
          :class="{ 'x-label-first': i === 0, 'x-label-last': i === xTicks.length - 1 }"
        >
          {{ tick.label }}
        </text>

        <!-- The temperature itself: a true baseline column chart, ECMWF-
             anomaly style — one independent column per measurement,
             rooted at 0°C, growing up or down from that line. No path, no
             staircase, no bridging between samples. -->
        <rect
          v-for="(col, i) in columns"
          :key="`col-${i}`"
          :x="col.x"
          :y="col.y"
          :width="col.width"
          :height="col.height"
          :fill="col.color"
          class="temp-column"
        />

        <!-- Crosshair -->
        <template v-if="hoveredReading">
          <line
            :x1="xScale(hoveredReading.received_at)"
            :x2="xScale(hoveredReading.received_at)"
            :y1="MARGIN.top"
            :y2="MARGIN.top + PLOT_H"
            class="crosshair"
            :class="{ locked: isPointLocked }"
          />
          <!-- Painted after the columns in DOM order, so it always sits on top
               (SVG has no z-index; paint order = source order). -->
          <circle
            :cx="xScale(hoveredReading.received_at)"
            :cy="yScale(hoveredReading.temperature)"
            :r="isPointLocked ? 6 : 4.5"
            class="hover-dot"
            :class="{ locked: isPointLocked }"
          />
        </template>
      </svg>

      <!-- Point tooltip: compact by design — temperature, date, time only -->
      <div v-if="hoveredReading" class="tooltip point-tooltip" :style="tooltipStyle">
        <div class="tooltip-temp">{{ fmtTemp(hoveredReading.temperature) }}</div>
        <div class="tooltip-date">{{ fmtDate(hoveredReading.received_at) }}</div>
        <div class="tooltip-time">{{ fmtTime(hoveredReading.received_at) }}</div>
      </div>

      <!-- Alarm popup: centered modal (not anchored to the marker) so it's
           readable and easy to dismiss with a thumb on mobile. Only one can
           be open at a time (hoveredMarker is a single ref); picking another
           marker just replaces it. -->
      <div v-if="hoveredMarker" class="alarm-modal-backdrop" @pointerdown.self="hoveredMarker = null">
        <div class="alarm-modal">
          <button type="button" class="alarm-modal-close" aria-label="Close" @click="hoveredMarker = null">✕</button>
          <div class="tooltip-title" :class="hoveredMarker.cls">{{ alarmTypeLabel(hoveredMarker.alarm.alarm_type) }}</div>
          <dl>
            <dt>Start</dt><dd>{{ fmtDate(hoveredMarker.alarm.triggered_at ?? hoveredMarker.alarm.detected_at) }} {{ fmtTime(hoveredMarker.alarm.triggered_at ?? hoveredMarker.alarm.detected_at) }}</dd>
            <dt>End</dt><dd>{{ hoveredMarker.alarm.resolved_at ? `${fmtDate(hoveredMarker.alarm.resolved_at)} ${fmtTime(hoveredMarker.alarm.resolved_at)}` : 'ongoing' }}</dd>
            <dt>Duration</dt><dd>{{ formatDuration(hoveredMarker.alarm.triggered_at ?? hoveredMarker.alarm.detected_at, hoveredMarker.alarm.resolved_at) }}</dd>
            <dt>Max</dt><dd>{{ fmtTemp(hoveredMarker.maxTemp) }}</dd>
            <dt>Min</dt><dd>{{ fmtTemp(hoveredMarker.minTemp) }}</dd>
          </dl>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.temp-chart {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.reset-zoom {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 3;
  background: #0c0e11;
  border: 1px solid #2a3138;
  border-radius: 6px;
  color: #8b95a1;
  font-size: 12px;
  font-weight: 400;
  padding: 5px 12px;
  cursor: pointer;
}
.reset-zoom:hover { border-color: #4a5560; color: #d5dce2; }

.state-message,
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #8fa1ba;
  text-align: center;
  min-height: 220px;
}

.empty-icon {
  width: 52px;
  height: 52px;
  fill: none;
  stroke: #3d5570;
  stroke-width: 1.4;
  margin-bottom: 14px;
}
.empty-title { font-size: 17px; color: #b9c9e6; margin: 0 0 8px; }
.empty-sub { font-size: 14px; margin: 2px 0; color: #8fa1ba; }
.empty-sub.offline { color: #ff6875; }
.empty-sub strong { color: #cdd9ee; font-weight: 500; }

.chart-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.chart-svg {
  width: 100%;
  height: 100%;
  touch-action: none;
  cursor: grab;
}
.chart-svg:active { cursor: grabbing; }

/* ─── Industrial SCADA/HMI look ──────────────────────────────────────
   One uniform matte-black/graphite background, no color fills of any
   kind behind the graph, a grid you have to look for, and the data line
   as the only thing that reads as "color" — everything else here is
   deliberately quiet so nothing competes with the measurement itself. */
.chart-bg { fill: #08090b; }

.grid-line { stroke: #232931; stroke-width: 1; opacity: 0.45; vector-effect: non-scaling-stroke; }

.threshold-line {
  stroke-width: 1;
  stroke-dasharray: 5 4;
  vector-effect: non-scaling-stroke;
  opacity: 0.55;
}
.threshold-high { stroke: #ef4444; }
.threshold-low { stroke: #3b82f6; }

.axis-label {
  fill: #626d79;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}
.x-label { text-anchor: middle; }
.x-label-first { text-anchor: start; }
.x-label-last { text-anchor: end; }

/* Baseline column chart: deliberately NOT crispEdges — at real point
   density the gap between columns is sub-pixel, and
   shape-rendering:crispEdges snaps rectangle edges to whole device
   pixels, which was silently swallowing that gap and fusing every column
   back into one continuous shape. Ordinary anti-aliasing keeps a
   sub-pixel gap visible as a faint seam instead. */
.temp-column { shape-rendering: auto; }

.chart-svg-live { cursor: default; }

/* Crosshair/hover-dot are neutral grays, not an accent color — the only
   "color" anywhere in this chart is the data line and the alarm-state
   red/blue, both of which mean something. A cursor doesn't need to. */
.crosshair { stroke: #3a4149; stroke-width: 1; stroke-dasharray: 4 4; vector-effect: non-scaling-stroke; opacity: 0.55; }
.crosshair.locked { stroke: #d5dce2; opacity: 0.9; }
.hover-dot { fill: #e9edf1; stroke: #0a0b0d; stroke-width: 1.25; vector-effect: non-scaling-stroke; }
.hover-dot.locked { fill: #ffffff; stroke: #0a0b0d; stroke-width: 1.5; }

.tooltip {
  position: absolute;
  z-index: 4;
  max-width: calc(100% - 12px);
  box-sizing: border-box;
  background: #0c0e11;
  border: 1px solid #23282e;
  border-radius: 8px;
  padding: 14px 16px;
  pointer-events: none;
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.45);
}
.tooltip-title { font-size: 13px; font-weight: 500; color: #a8b1bb; text-transform: uppercase; margin-bottom: 9px; letter-spacing: 0.04em; }
.tooltip-title.marker-high { color: #ef4444; }
.tooltip-title.marker-low { color: #3b82f6; }
.tooltip-title.marker-offline { color: #7b8792; }
.tooltip dl { display: grid; grid-template-columns: auto auto; gap: 5px 16px; margin: 0; }
.tooltip dt { font-size: 13px; color: #626d79; }
.tooltip dd { margin: 0; font-size: 13px; color: #e9edf1; font-weight: 400; text-align: right; font-variant-numeric: tabular-nums; }
.tooltip dd.status-bad { color: #ef4444; }

.point-tooltip { min-width: 150px; }
.tooltip-temp { font-size: 22px; font-weight: 600; color: #e9edf1; line-height: 1; margin-bottom: 6px; font-variant-numeric: tabular-nums; }
.tooltip-date, .tooltip-time { font-size: 13px; color: #626d79; }

/* Alarm popup: a centered modal, not anchored to the marker — dark
   backdrop, ~80-90% viewport width on mobile (capped on larger screens),
   closed by the X button, tapping the backdrop, or tapping the same
   marker again. */
.alarm-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(3, 9, 16, 0.72);
  padding: 20px;
}
.alarm-modal {
  position: relative;
  width: min(88vw, 420px);
  max-height: 85vh;
  overflow: auto;
  background: #0c0e11;
  border: 1px solid #23282e;
  border-radius: 14px;
  padding: 24px 20px 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.alarm-modal-close {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #14171b;
  border: 1px solid #262c33;
  border-radius: 50%;
  color: #8b95a1;
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
}
.alarm-modal-close:hover { border-color: #4a5560; color: #d5dce2; }
.alarm-modal .tooltip-title { font-size: 15px; margin: 0 26px 16px 0; }
.alarm-modal dl { display: grid; grid-template-columns: auto auto; gap: 10px 20px; margin: 0; }
.alarm-modal dt { font-size: 14px; color: #626d79; }
.alarm-modal dd { margin: 0; font-size: 14px; color: #e9edf1; font-weight: 400; text-align: right; font-variant-numeric: tabular-nums; }

@media (max-width: 800px) {
  /* Smaller than the old default (20px) but deliberately not as small as
     this typeface can go on desktop — "mobile readability" is an explicit
     requirement, and axis text is the first thing to become illegible on
     a phone, not the place to chase minimalism. */
  .axis-label { font-size: 17px; }
  .tooltip { padding: 12px 14px; }
  .tooltip dt, .tooltip dd { font-size: 12px; }
  .tooltip-temp { font-size: 20px; }
}
</style>
