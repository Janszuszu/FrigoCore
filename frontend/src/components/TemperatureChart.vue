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
const VB_W = 1000
const VB_H = 360
const MARGIN = { top: 16, right: 16, bottom: 58, left: 58 }
const PLOT_W = VB_W - MARGIN.left - MARGIN.right
const PLOT_H = VB_H - MARGIN.top - MARGIN.bottom
const STRIP_Y = MARGIN.top + PLOT_H + 10
const STRIP_H = 16
const XLABEL_Y = STRIP_Y + STRIP_H + 20

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

const yTicks = computed(() => {
  const { min, max, step } = yDomain.value
  const ticks: number[] = []
  for (let v = min; v <= max + step * 0.001; v += step) ticks.push(Math.round(v * 100) / 100)
  return ticks
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

// ─── Responsive tick count — fewer labels on narrow viewports so they
// never overlap; same lever drives both historical and LIVE ticks. ────
const viewportWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1280)
function onViewportResize() {
  viewportWidth.value = window.innerWidth
}
const tickCount = computed(() => (viewportWidth.value < 480 ? 3 : viewportWidth.value < 900 ? 5 : 6))

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
// 1H/24H time-of-day, 7D calendar dates) since that's what the user is
// deliberately asking to see regardless of how much data is actually
// loaded. Any range this component doesn't know about yet (or a zoomed
// slice) falls back to a span-based auto choice so it's never wrong:
// minutes/hours -> time, days -> dates, months -> month + day. A chart
// spanning more than a day never shows hour-only labels.
const MINUTE_MS = 60 * 1000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

function formatAxisTime(ms: number, spanMs: number): string {
  const d = new Date(ms)
  if (props.range === 'LIVE') {
    return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }
  if (props.range === '1H' || props.range === '24H') {
    return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })
  }
  if (props.range === '7D') {
    const opts: Intl.DateTimeFormatOptions = { day: '2-digit', month: '2-digit' }
    if (viewportWidth.value >= 900) opts.weekday = 'short'
    return d.toLocaleDateString('pl-PL', opts)
  }
  // Auto fallback (e.g. a zoomed-in slice, or a future range) — never
  // show hour-only labels once the span crosses a day.
  if (spanMs <= DAY_MS) return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })
  if (spanMs <= 90 * DAY_MS) return d.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })
  return d.toLocaleDateString('pl-PL', { day: '2-digit', month: 'short' })
}

// ─── Monotone cubic Hermite spline (Fritsch–Carlson) ───────────────
// Unlike a plain Catmull-Rom spline, the monotonicity constraint below
// clamps each segment's tangents so the curve never rings past a data
// point's actual value — it stays smooth without ever overshooting.
function buildMonotonePath(pts: { x: number; y: number }[]): string {
  const n = pts.length
  if (n === 0) return ''
  if (n === 1) return `M${pts[0].x},${pts[0].y}`
  if (n === 2) return `M${pts[0].x},${pts[0].y} L${pts[1].x},${pts[1].y}`

  const dx: number[] = new Array(n - 1)
  const slope: number[] = new Array(n - 1)
  for (let i = 0; i < n - 1; i++) {
    dx[i] = pts[i + 1].x - pts[i].x
    const dy = pts[i + 1].y - pts[i].y
    slope[i] = dx[i] !== 0 ? dy / dx[i] : 0
  }

  const m: number[] = new Array(n)
  m[0] = slope[0]
  m[n - 1] = slope[n - 2]
  for (let i = 1; i < n - 1; i++) {
    m[i] = slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2
  }

  // Fritsch–Carlson monotonicity constraint — the actual no-overshoot guarantee.
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      m[i] = 0
      m[i + 1] = 0
      continue
    }
    const a = m[i] / slope[i]
    const b = m[i + 1] / slope[i]
    const h = Math.hypot(a, b)
    if (h > 3) {
      const tau = 3 / h
      m[i] = tau * a * slope[i]
      m[i + 1] = tau * b * slope[i]
    }
  }

  let d = `M${pts[0].x},${pts[0].y}`
  for (let i = 0; i < n - 1; i++) {
    const p0 = pts[i]
    const p1 = pts[i + 1]
    const cp1x = p0.x + dx[i] / 3
    const cp1y = p0.y + (m[i] * dx[i]) / 3
    const cp2x = p1.x - dx[i] / 3
    const cp2y = p1.y - (m[i + 1] * dx[i]) / 3
    d += ` C${cp1x},${cp1y} ${cp2x},${cp2y} ${p1.x},${p1.y}`
  }
  return d
}

// ─── Render-point decimation ────────────────────────────────────────
// Keeps the rendered path tractable with 10k+ historical points without
// touching the domain/tooltip/marker logic, which still use the full-
// fidelity `visible` array. Min/max-per-bucket (not a stride/average)
// so real excursions above/below a threshold are never smoothed away.
const RENDER_POINT_BUDGET = 2000

function decimateForRender<T extends { x: number; y: number }>(points: T[], maxPoints: number): T[] {
  if (points.length <= maxPoints) return points
  const bucketSize = Math.ceil(points.length / (maxPoints / 2))
  const result: T[] = []
  for (let i = 0; i < points.length; i += bucketSize) {
    const bucket = points.slice(i, i + bucketSize)
    if (!bucket.length) continue
    let minP = bucket[0]
    let maxP = bucket[0]
    for (const p of bucket) {
      if (p.y < minP.y) minP = p
      if (p.y > maxP.y) maxP = p
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

const linePath = computed(() => {
  const d = visible.value
  if (d.length < 2) return ''
  const pts = d.map((r) => ({ x: xScale(r.received_at), y: yScale(r.temperature) }))
  return buildMonotonePath(decimateForRender(pts, RENDER_POINT_BUDGET))
})

// ─── Threshold-anchored color story ────────────────────────────────
// Below LOW -> blue, normal -> cyan, approaching HIGH -> yellow, above
// HIGH -> red. Rendered as a single vertical gradient stroke rather than
// hard-clipped overlay paths: cheaper (one path, no extra clip-path
// geometry per zone) and reads as the smooth SCADA-style blend the
// reference design calls for, while every pivot color is still pinned
// to an exact, real threshold value — nothing about the anchor points
// is approximate, only the blend width between them is stylistic.
const LINE_COLOR_LOW = '#4ea8ff'
const LINE_COLOR_NORMAL = '#0edbe5'
const LINE_COLOR_APPROACHING = '#ffd23f'
const LINE_COLOR_HIGH = '#ff4d4f'
const APPROACH_BUFFER_FRACTION = 0.15

interface GradientStop {
  offset: number
  color: string
}

function buildLineGradientStops(
  scaleFn: (temp: number) => number,
  domainMin: number,
  domainMax: number,
  lowT: number | null,
  highT: number | null,
): GradientStop[] {
  if (lowT == null && highT == null) {
    return [
      { offset: 0, color: LINE_COLOR_NORMAL },
      { offset: 1, color: LINE_COLOR_NORMAL },
    ]
  }
  const topY = scaleFn(domainMax)
  const bottomY = scaleFn(domainMin)
  const span = bottomY - topY || 1
  const offsetFor = (temp: number) => Math.min(1, Math.max(0, (scaleFn(temp) - topY) / span))
  const refLow = lowT ?? domainMin
  const refHigh = highT ?? domainMax
  const buffer = (refHigh - refLow) * APPROACH_BUFFER_FRACTION

  const stops: GradientStop[] = [{ offset: 0, color: highT != null ? LINE_COLOR_HIGH : LINE_COLOR_NORMAL }]
  if (highT != null) {
    const approaching = highT - buffer
    stops.push({ offset: offsetFor(highT), color: LINE_COLOR_HIGH })
    stops.push({ offset: offsetFor(approaching), color: LINE_COLOR_APPROACHING })
    stops.push({ offset: offsetFor(approaching), color: LINE_COLOR_NORMAL })
  }
  if (lowT != null) {
    stops.push({ offset: offsetFor(lowT), color: LINE_COLOR_NORMAL })
    stops.push({ offset: offsetFor(lowT), color: LINE_COLOR_LOW })
  }
  stops.push({ offset: 1, color: lowT != null ? LINE_COLOR_LOW : LINE_COLOR_NORMAL })

  // SVG gradients require non-decreasing offsets — clamp in case a
  // threshold sits outside the (padded) visible domain.
  for (let i = 1; i < stops.length; i++) {
    if (stops[i].offset < stops[i - 1].offset) stops[i].offset = stops[i - 1].offset
  }
  return stops
}

interface ZoneInfo {
  gradientStops: GradientStop[]
  normalLow: number | null
  normalHigh: number | null
  normalLineY: number | null
}

function buildZoneInfo(
  scaleFn: (temp: number) => number,
  domainMin: number,
  domainMax: number,
  lowT: number | null,
  highT: number | null,
): ZoneInfo {
  const gradientStops = buildLineGradientStops(scaleFn, domainMin, domainMax, lowT, highT)
  if (lowT == null && highT == null) {
    return { gradientStops, normalLow: null, normalHigh: null, normalLineY: null }
  }
  const refLow = lowT ?? domainMin
  const refHigh = highT ?? domainMax
  const buffer = (refHigh - refLow) * APPROACH_BUFFER_FRACTION
  const normalLow = lowT != null ? lowT + buffer : null
  const normalHigh = highT != null ? highT - buffer : null
  const midTemp = ((normalLow ?? domainMin) + (normalHigh ?? domainMax)) / 2
  return { gradientStops, normalLow, normalHigh, normalLineY: scaleFn(midTemp) }
}

const zoneInfo = computed(() =>
  buildZoneInfo(yScale, yDomain.value.min, yDomain.value.max, props.lowThreshold, props.highThreshold),
)

function fmtSigned(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}°C`
}

const areaPath = computed(() => {
  if (!linePath.value || !visible.value.length) return ''
  const d = visible.value
  const first = xScale(d[0].received_at)
  const last = xScale(d[d.length - 1].received_at)
  const floor = MARGIN.top + PLOT_H
  return `${linePath.value} L${last},${floor} L${first},${floor} Z`
})

// ─── LIVE mode: oscilloscope-style sweep ──────────────────────────
// Independent of the historical zoom/pan/linePath machinery above. The
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
  const ticks: number[] = []
  for (let v = min; v <= max + step * 0.001; v += step) ticks.push(Math.round(v * 100) / 100)
  return ticks
})

function liveYScale(temp: number): number {
  const { min, max } = liveYDomain.value
  const span = max - min || 1
  return MARGIN.top + PLOT_H - ((temp - min) / span) * PLOT_H
}

// Recomputed only when livePoints/thresholds actually change (i.e. on a
// real new measurement) — NOT on the 60fps `liveNow` tick, which only
// drives the cheap shift transform below.
const liveLinePath = computed(() => {
  const pts = livePoints.value.map((p) => ({ x: liveRawX(p.t), y: liveYScale(p.temp) }))
  return buildMonotonePath(pts)
})

function resetLive() {
  livePoints.value = []
  liveSweepStart.value = Date.now()
  liveNow.value = liveSweepStart.value
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
  const windowStart = liveNow.value - LIVE_WINDOW_MS
  const ticks: { x: number; label: string }[] = []
  for (let i = 0; i <= count; i++) {
    const t = windowStart + (LIVE_WINDOW_MS * i) / count
    ticks.push({ x: liveRawX(t) + liveShiftPx.value, label: liveTickLabel(i, t) })
  }
  return ticks
})

const liveZoneInfo = computed(() =>
  buildZoneInfo(liveYScale, liveYDomain.value.min, liveYDomain.value.max, props.lowThreshold, props.highThreshold),
)

const liveZones = computed(() =>
  buildZones(liveYScale, liveYDomain.value.min, liveYDomain.value.max, props.lowThreshold, props.highThreshold),
)

watch(isLive, (live) => {
  if (live) {
    resetLive()
    startLiveClock()
  } else {
    stopLiveClock()
  }
}, { immediate: true })

// Unified readings watcher: LIVE mode appends only the new tail (no zoom/
// selection to reset — both are disabled in LIVE); historical ranges keep
// the old full-reset behavior when the parent swaps in a new snapshot.
watch(
  () => props.readings,
  (newR, oldR) => {
    if (!isLive.value) {
      zoomStart.value = 0
      zoomEnd.value = 1
      clearSelection()
      return
    }
    const old = oldR ?? []
    if (newR.length === 0) {
      resetLive()
      return
    }
    const grewInPlace = newR.length > old.length
    const tail = grewInPlace ? newR.slice(old.length) : newR
    if (!grewInPlace) resetLive()
    for (const r of tail) {
      if (typeof r.temperature === 'number' && !Number.isNaN(r.temperature)) {
        appendLivePoint(new Date(r.received_at).getTime(), r.temperature)
      }
    }
  },
)


// ─── Background zones — subtle shading for the three alarm bands ───
function buildZones(
  scaleFn: (temp: number) => number,
  domainMin: number,
  domainMax: number,
  lowT: number | null,
  highT: number | null,
): { y: number; height: number; className: string }[] {
  const top = MARGIN.top
  const bottom = MARGIN.top + PLOT_H
  const zonesList: { y: number; height: number; className: string }[] = []
  if (highT != null && highT < domainMax) {
    const y = scaleFn(Math.min(highT, domainMax))
    zonesList.push({ y: top, height: Math.max(y - top, 0), className: 'zone-high' })
  }
  if (lowT != null && lowT > domainMin) {
    const y = scaleFn(Math.max(lowT, domainMin))
    zonesList.push({ y, height: Math.max(bottom - y, 0), className: 'zone-low' })
  }
  const normalTop = highT != null ? scaleFn(Math.min(highT, domainMax)) : top
  const normalBottom = lowT != null ? scaleFn(Math.max(lowT, domainMin)) : bottom
  if (normalBottom > normalTop) {
    zonesList.push({ y: normalTop, height: normalBottom - normalTop, className: 'zone-normal' })
  }
  return zonesList
}

const zones = computed(() =>
  buildZones(yScale, yDomain.value.min, yDomain.value.max, props.lowThreshold, props.highThreshold),
)

// ─── Alarm timeline markers ─────────────────────────────────────
const ALARM_GLYPH: Record<string, string> = {
  high_temperature: '▲',
  low_temperature: '▼',
  offline: '■',
}
const ALARM_CLASS: Record<string, string> = {
  high_temperature: 'marker-high',
  low_temperature: 'marker-low',
  offline: 'marker-offline',
}

const markers = computed(() => {
  const { start, end } = xDomain.value
  return props.alarms
    .map((alarm) => {
      const startMs = new Date(alarm.triggered_at ?? alarm.detected_at).getTime()
      const endMs = alarm.resolved_at ? new Date(alarm.resolved_at).getTime() : null
      if (endMs != null && endMs < start) return null
      if (startMs > end) return null
      const windowEnd = endMs ?? Date.now()
      const inWindow = validReadings.value.filter((r) => {
        const t = new Date(r.received_at).getTime()
        return t >= startMs && t <= windowEnd
      })
      const temps = inWindow.map((r) => r.temperature)
      return {
        alarm,
        x1: xScaleMs(startMs),
        x2: endMs != null ? xScaleMs(endMs) : null,
        glyph: ALARM_GLYPH[alarm.alarm_type] ?? '●',
        cls: ALARM_CLASS[alarm.alarm_type] ?? 'marker-offline',
        maxTemp: temps.length ? Math.max(...temps) : null,
        minTemp: temps.length ? Math.min(...temps) : null,
      }
    })
    .filter((m): m is NonNullable<typeof m> => m !== null)
})

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
const hoveredMarker = ref<(typeof markers.value)[number] | null>(null)
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
  hoveredMarker.value = null
  dragStartZoom.value = { start: zoomStart.value, end: zoomEnd.value }
  tryCapturePointer(e.target, e.pointerId)

  if (e.pointerType === 'mouse') {
    dragging.value = true
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

function onPointerUp(e: PointerEvent) {
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

// viewportWidth is read (not used numerically) purely to give these
// computeds a reactive dependency on the viewport — without it, resizing
// or rotating the device wouldn't reposition an already-open tooltip or
// the always-on latest-value badge, since svgEl.getBoundingClientRect()
// is read imperatively and isn't itself reactive.
const tooltipStyle = computed(() => {
  void viewportWidth.value
  return positionFromViewBox(tooltipPos.value.x, tooltipPos.value.y)
})

const markerTooltipStyle = computed(() => {
  void viewportWidth.value
  const m = hoveredMarker.value
  if (!m) return {}
  return positionFromViewBox(m.x1, STRIP_Y)
})

// ─── Latest-value marker — always visible, independent of hover/tap ─
const latestReading = computed(() => {
  if (isLive.value) {
    const p = livePoints.value[livePoints.value.length - 1]
    if (!p) return null
    return { x: Math.min(liveRawX(p.t) + liveShiftPx.value, MARGIN.left + PLOT_W), y: liveYScale(p.temp), temp: p.temp }
  }
  const d = visible.value
  if (!d.length) return null
  const last = d[d.length - 1]
  return { x: xScale(last.received_at), y: yScale(last.temperature), temp: last.temperature }
})

// Compact variant of positionFromViewBox: centers vertically on the point
// (rather than offsetting above it) and assumes a much smaller box, since
// this is a short value badge, not a multi-line tooltip.
function badgePositionFromViewBox(vbX: number, vbY: number, boxWidth = 92, boxHeight = 30): { left: string; top: string } {
  const el = svgEl.value
  if (!el) return { left: '0px', top: '0px' }
  const rect = el.getBoundingClientRect()
  const pxPerVbX = rect.width / VB_W
  const pxPerVbY = rect.height / VB_H
  let left = vbX * pxPerVbX + 12
  if (left + boxWidth > rect.width) left = Math.max(0, vbX * pxPerVbX - boxWidth - 12)
  left = Math.min(left, Math.max(0, rect.width - boxWidth))
  const top = Math.max(0, Math.min(vbY * pxPerVbY - boxHeight / 2, rect.height - boxHeight))
  return { left: `${left}px`, top: `${top}px` }
}

const latestBadgeStyle = computed(() => {
  void viewportWidth.value
  const r = latestReading.value
  if (!r) return {}
  return badgePositionFromViewBox(r.x, r.y)
})

// A locked (touch-selected) tooltip only closes on: another selection
// (handled in selectAt), the chart's data changing (handled in the
// readings watcher), or a tap outside the chart — handled here.
function onDocumentPointerDown(e: PointerEvent) {
  if (!isPointLocked.value) return
  if (rootEl.value && !rootEl.value.contains(e.target as Node)) clearSelection()
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown, true)
  window.addEventListener('resize', onViewportResize)
})
onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown, true)
  window.removeEventListener('resize', onViewportResize)
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
          <linearGradient id="line-gradient" gradientUnits="userSpaceOnUse" :x1="MARGIN.left" :y1="MARGIN.top" :x2="MARGIN.left" :y2="MARGIN.top + PLOT_H">
            <stop v-for="(s, i) in liveZoneInfo.gradientStops" :key="i" :offset="s.offset" :stop-color="s.color" />
          </linearGradient>
        </defs>

        <!-- Background zones -->
        <rect
          v-for="(z, i) in liveZones"
          :key="`live-zone-${i}`"
          :x="MARGIN.left"
          :y="z.y"
          :width="PLOT_W"
          :height="z.height"
          :class="z.className"
        />

        <!-- Grid + thresholds stay fixed in place — only the data sweeps -->
        <line
          v-for="t in liveYTicks"
          :key="`live-grid-${t}`"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="liveYScale(t)"
          :y2="liveYScale(t)"
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
          v-if="liveZoneInfo.normalLineY != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="liveZoneInfo.normalLineY"
          :y2="liveZoneInfo.normalLineY"
          class="threshold-line threshold-normal"
        />
        <line
          v-if="lowThreshold != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="liveYScale(lowThreshold)"
          :y2="liveYScale(lowThreshold)"
          class="threshold-line threshold-low"
        />

        <!-- Left-side zone labels -->
        <text v-if="highThreshold != null" :x="MARGIN.left + 8" :y="liveYScale(highThreshold) - 8" class="zone-label zone-label-alarm">
          ALARM HIGH&#160;&#160;{{ fmtSigned(highThreshold) }}
        </text>
        <text v-if="liveZoneInfo.normalLineY != null" :x="MARGIN.left + 8" :y="liveZoneInfo.normalLineY - 8" class="zone-label zone-label-normal">
          NORMAL&#160;&#160;{{ fmtSigned(liveZoneInfo.normalLow ?? liveYDomain.min) }} – {{ fmtSigned(liveZoneInfo.normalHigh ?? liveYDomain.max) }}
        </text>
        <text v-if="lowThreshold != null" :x="MARGIN.left + 8" :y="liveYScale(lowThreshold) - 8" class="zone-label zone-label-alarm">
          ALARM LOW&#160;&#160;{{ fmtSigned(lowThreshold) }}
        </text>

        <text v-for="t in liveYTicks" :key="`live-ylabel-${t}`" :x="MARGIN.left - 10" :y="liveYScale(t)" class="axis-label y-label">
          {{ t.toFixed(liveYDomain.step < 1 ? 1 : 0) }}°
        </text>
        <text v-for="(tick, i) in liveXTicks" :key="`live-xlabel-${i}`" :x="tick.x" :y="XLABEL_Y" class="axis-label x-label">
          {{ tick.label }}
        </text>

        <!-- The sweep itself: clipped to the plot rect and shifted left as
             the window fills, so it visibly scrolls off at the left edge
             like an oscilloscope trace. liveLinePath only recomputes when
             a real point arrives; liveShiftPx (this transform) is the one
             thing driven by the 60fps clock. The gradient stroke costs
             nothing extra per frame — it's a static def, not per-point. -->
        <g clip-path="url(#plot-area-clip)">
          <g class="live-sweep" :transform="`translate(${liveShiftPx},0)`">
            <path :d="liveLinePath" class="line-path" />
          </g>
        </g>

        <!-- Latest value: always-on marker, independent of hover/tap -->
        <circle v-if="latestReading" :cx="latestReading.x" :cy="latestReading.y" r="4.5" class="latest-dot" />
      </svg>
      <div v-if="latestReading" class="latest-badge" :style="latestBadgeStyle">{{ fmtSigned(latestReading.temp) }}</div>
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
        <defs>
          <linearGradient id="area-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#0edbe5" stop-opacity="0.28" />
            <stop offset="100%" stop-color="#0edbe5" stop-opacity="0" />
          </linearGradient>
          <linearGradient id="line-gradient" gradientUnits="userSpaceOnUse" :x1="MARGIN.left" :y1="MARGIN.top" :x2="MARGIN.left" :y2="MARGIN.top + PLOT_H">
            <stop v-for="(s, i) in zoneInfo.gradientStops" :key="i" :offset="s.offset" :stop-color="s.color" />
          </linearGradient>
        </defs>

        <!-- Background zones -->
        <rect
          v-for="(z, i) in zones"
          :key="`zone-${i}`"
          :x="MARGIN.left"
          :y="z.y"
          :width="PLOT_W"
          :height="z.height"
          :class="z.className"
        />

        <!-- Horizontal grid -->
        <line
          v-for="t in yTicks"
          :key="`grid-${t}`"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="yScale(t)"
          :y2="yScale(t)"
          class="grid-line"
        />

        <!-- Threshold lines (visually distinct from grid: dashed + color) -->
        <line
          v-if="highThreshold != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="yScale(highThreshold)"
          :y2="yScale(highThreshold)"
          class="threshold-line threshold-high"
        />
        <line
          v-if="zoneInfo.normalLineY != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="zoneInfo.normalLineY"
          :y2="zoneInfo.normalLineY"
          class="threshold-line threshold-normal"
        />
        <line
          v-if="lowThreshold != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="yScale(lowThreshold)"
          :y2="yScale(lowThreshold)"
          class="threshold-line threshold-low"
        />

        <!-- Left-side zone labels -->
        <text v-if="highThreshold != null" :x="MARGIN.left + 8" :y="yScale(highThreshold) - 8" class="zone-label zone-label-alarm">
          ALARM HIGH&#160;&#160;{{ fmtSigned(highThreshold) }}
        </text>
        <text v-if="zoneInfo.normalLineY != null" :x="MARGIN.left + 8" :y="zoneInfo.normalLineY - 8" class="zone-label zone-label-normal">
          NORMAL&#160;&#160;{{ fmtSigned(zoneInfo.normalLow ?? yDomain.min) }} – {{ fmtSigned(zoneInfo.normalHigh ?? yDomain.max) }}
        </text>
        <text v-if="lowThreshold != null" :x="MARGIN.left + 8" :y="yScale(lowThreshold) - 8" class="zone-label zone-label-alarm">
          ALARM LOW&#160;&#160;{{ fmtSigned(lowThreshold) }}
        </text>

        <!-- Y axis labels -->
        <text v-for="t in yTicks" :key="`ylabel-${t}`" :x="MARGIN.left - 10" :y="yScale(t)" class="axis-label y-label">
          {{ t.toFixed(yDomain.step < 1 ? 1 : 0) }}°
        </text>

        <!-- X axis labels -->
        <text v-for="(tick, i) in xTicks" :key="`xlabel-${i}`" :x="tick.x" :y="XLABEL_Y" class="axis-label x-label">
          {{ tick.label }}
        </text>

        <!-- Area + line -->
        <path :d="areaPath" class="area-fill" />
        <path :d="linePath" class="line-path" />

        <!-- Alarm timeline strip -->
        <line :x1="MARGIN.left" :x2="VB_W - MARGIN.right" :y1="STRIP_Y + STRIP_H / 2" :y2="STRIP_Y + STRIP_H / 2" class="strip-baseline" />
        <g v-for="(m, i) in markers" :key="`marker-${i}`">
          <line
            v-if="m.x2 != null"
            :x1="m.x1"
            :x2="m.x2"
            :y1="STRIP_Y + STRIP_H / 2"
            :y2="STRIP_Y + STRIP_H / 2"
            class="marker-span"
            :class="m.cls"
          />
          <text
            :x="m.x1"
            :y="STRIP_Y + STRIP_H - 3"
            class="marker-glyph"
            :class="m.cls"
            @mouseenter="hoveredMarker = m"
            @mouseleave="hoveredMarker = null"
          >{{ m.glyph }}</text>
          <circle
            v-if="m.x2 != null"
            :cx="m.x2"
            :cy="STRIP_Y + STRIP_H / 2"
            r="3.2"
            class="marker-resolved"
            @mouseenter="hoveredMarker = m"
            @mouseleave="hoveredMarker = null"
          />
        </g>

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
          <!-- Painted after line-path/area-fill in DOM order, so it always
               sits on top (SVG has no z-index; paint order = source order). -->
          <circle
            :cx="xScale(hoveredReading.received_at)"
            :cy="yScale(hoveredReading.temperature)"
            :r="isPointLocked ? 6 : 4.5"
            class="hover-dot"
            :class="{ locked: isPointLocked }"
          />
        </template>

        <!-- Latest value: always-on marker, independent of hover/tap -->
        <circle v-if="latestReading" :cx="latestReading.x" :cy="latestReading.y" r="4.5" class="latest-dot" />
      </svg>

      <div v-if="latestReading" class="latest-badge" :style="latestBadgeStyle">{{ fmtSigned(latestReading.temp) }}</div>

      <!-- Point tooltip: compact by design — temperature, date, time only -->
      <div v-if="hoveredReading" class="tooltip point-tooltip" :style="tooltipStyle">
        <div class="tooltip-temp">{{ fmtTemp(hoveredReading.temperature) }}</div>
        <div class="tooltip-date">{{ fmtDate(hoveredReading.received_at) }}</div>
        <div class="tooltip-time">{{ fmtTime(hoveredReading.received_at) }}</div>
      </div>

      <!-- Alarm marker tooltip -->
      <div v-if="hoveredMarker" class="tooltip marker-tooltip" :style="markerTooltipStyle">
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
  background: #081421;
  border: 1px solid #29455e;
  border-radius: 6px;
  color: #b9c9e6;
  font-size: 12px;
  padding: 5px 12px;
  cursor: pointer;
}
.reset-zoom:hover { border-color: #00cce3; color: #00e5ef; }

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

.zone-high { fill: rgba(255, 104, 117, 0.07); }
.zone-low { fill: rgba(78, 168, 255, 0.07); }
.zone-normal { fill: rgba(0, 231, 123, 0.035); }

.grid-line { stroke: #14293c; stroke-width: 1; vector-effect: non-scaling-stroke; }

.threshold-line {
  stroke-width: 1.4;
  stroke-dasharray: 7 5;
  vector-effect: non-scaling-stroke;
  opacity: 0.75;
}
.threshold-high { stroke: #ff6875; }
.threshold-low { stroke: #4ea8ff; }
.threshold-normal { stroke: #00e77b; opacity: 0.5; }

.zone-label {
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-anchor: start;
}
.zone-label-alarm { fill: #ff6875; }
.zone-label-normal { fill: #00e77b; }

.axis-label { fill: #9cadc7; font-size: 16.5px; }
.y-label { text-anchor: end; dominant-baseline: middle; }
.x-label { text-anchor: middle; }

.area-fill { fill: url(#area-gradient); opacity: 0.5; }
.line-path {
  fill: none;
  stroke: url(#line-gradient);
  stroke-width: 3.2;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.chart-svg-live { cursor: default; }
.latest-dot { fill: #0edbe5; stroke: #071620; stroke-width: 1.5; vector-effect: non-scaling-stroke; }
.latest-badge {
  position: absolute;
  z-index: 3;
  background: #0a1827;
  border: 1px solid #0edbe5;
  border-radius: 14px;
  padding: 4px 10px;
  font-size: 13px;
  font-weight: 700;
  color: #0edbe5;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
  font-variant-numeric: tabular-nums;
}

.strip-baseline { stroke: #1a2f43; stroke-width: 1; vector-effect: non-scaling-stroke; }
.marker-span { stroke-width: 2; vector-effect: non-scaling-stroke; opacity: 0.6; }
.marker-glyph { font-size: 13px; text-anchor: middle; cursor: pointer; }
.marker-resolved { fill: #00e77b; cursor: pointer; }

.marker-high, .marker-high.marker-span { fill: #ff6875; stroke: #ff6875; }
.marker-low, .marker-low.marker-span { fill: #4ea8ff; stroke: #4ea8ff; }
.marker-offline, .marker-offline.marker-span { fill: #8fa1ba; stroke: #8fa1ba; }

.crosshair { stroke: #8fa1ba; stroke-width: 1; stroke-dasharray: 4 4; vector-effect: non-scaling-stroke; opacity: 0.6; }
.crosshair.locked { stroke: #0edbe5; opacity: 0.85; }
.hover-dot { fill: #0edbe5; stroke: #071620; stroke-width: 1.5; vector-effect: non-scaling-stroke; }
.hover-dot.locked { stroke: #eafeff; stroke-width: 1.5; }

.tooltip {
  position: absolute;
  z-index: 4;
  max-width: calc(100% - 12px);
  box-sizing: border-box;
  background: #0a1827;
  border: 1px solid #26516b;
  border-radius: 8px;
  padding: 14px 16px;
  pointer-events: none;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}
.tooltip-title { font-size: 14px; font-weight: 600; color: #00dde1; text-transform: uppercase; margin-bottom: 9px; letter-spacing: 0.03em; }
.tooltip-title.marker-high { color: #ff6875; }
.tooltip-title.marker-low { color: #4ea8ff; }
.tooltip-title.marker-offline { color: #8fa1ba; }
.tooltip dl { display: grid; grid-template-columns: auto auto; gap: 5px 16px; margin: 0; }
.tooltip dt { font-size: 13px; color: #8fa1ba; }
.tooltip dd { margin: 0; font-size: 13px; color: #e8effa; text-align: right; font-variant-numeric: tabular-nums; }
.tooltip dd.status-bad { color: #ff6875; }

.point-tooltip { min-width: 150px; }
.tooltip-temp { font-size: 24px; font-weight: 700; color: #0edbe5; line-height: 1; margin-bottom: 6px; font-variant-numeric: tabular-nums; }
.tooltip-date, .tooltip-time { font-size: 13px; color: #9aabc5; }

@media (max-width: 800px) {
  .axis-label { font-size: 20px; }
  .zone-label { font-size: 15px; }
  .tooltip { padding: 12px 14px; }
  .tooltip dt, .tooltip dd { font-size: 12px; }
  .tooltip-temp { font-size: 20px; }
  .latest-badge { font-size: 12px; padding: 3px 8px; }
}
</style>
