<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AlarmItem, MeasurementItem, SensorItem } from '@/types'

const props = defineProps<{
  sensor: SensorItem
  readings: MeasurementItem[] // ascending by received_at (oldest first)
  highThreshold: number | null
  lowThreshold: number | null
  alarms: AlarmItem[] // this sensor's alarms overlapping the visible range
  activeAlarmLabel: string | null
  online: boolean
  loading: boolean
}>()

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
const zoomStart = ref(0)
const zoomEnd = ref(1)

watch(
  () => props.readings,
  () => {
    zoomStart.value = 0
    zoomEnd.value = 1
  },
)

const visible = computed(() => {
  const d = validReadings.value
  if (d.length < 2) return d
  const startIdx = Math.floor(zoomStart.value * (d.length - 1))
  const endIdx = Math.ceil(zoomEnd.value * (d.length - 1))
  return d.slice(startIdx, Math.max(endIdx + 1, startIdx + 2))
})

const isZoomed = computed(() => zoomStart.value > 0.001 || zoomEnd.value < 0.999)

// ─── Trend (based on the most recent points in the full series) ───
const trend = computed<{ dir: 'up' | 'down' | 'flat'; label: string; glyph: string }>(() => {
  const d = validReadings.value
  const sample = d.slice(-8)
  if (sample.length < 3) return { dir: 'flat', label: 'Stable', glyph: '➡' }
  const n = sample.length
  const xs = sample.map((_, i) => i)
  const ys = sample.map((r) => r.temperature)
  const xMean = xs.reduce((a, b) => a + b, 0) / n
  const yMean = ys.reduce((a, b) => a + b, 0) / n
  let num = 0
  let den = 0
  for (let i = 0; i < n; i++) {
    num += (xs[i] - xMean) * (ys[i] - yMean)
    den += (xs[i] - xMean) ** 2
  }
  const slope = den === 0 ? 0 : num / den
  if (slope > 0.04) return { dir: 'up', label: 'Rising', glyph: '⬈' }
  if (slope < -0.04) return { dir: 'down', label: 'Falling', glyph: '⬊' }
  return { dir: 'flat', label: 'Stable', glyph: '➡' }
})

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

const xTicks = computed(() => {
  const { start, end } = xDomain.value
  const count = 6
  const spanMs = end - start
  const ticks: { x: number; label: string }[] = []
  for (let i = 0; i <= count; i++) {
    const t = start + (spanMs * i) / count
    ticks.push({ x: xScaleMs(t), label: formatAxisTime(t, spanMs) })
  }
  return ticks
})

function formatAxisTime(ms: number, spanMs: number): string {
  const d = new Date(ms)
  if (spanMs > 36 * 60 * 60 * 1000) {
    return d.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })
  }
  if (spanMs > 3 * 60 * 60 * 1000) {
    return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// ─── Smoothed line path (lightweight midpoint quadratic smoothing) ─
const linePath = computed(() => {
  const d = visible.value
  if (d.length < 2) return ''
  const pts = d.map((r) => [xScale(r.received_at), yScale(r.temperature)] as const)
  let path = `M${pts[0][0]},${pts[0][1]}`
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1]
    const [x1, y1] = pts[i]
    const mx = (x0 + x1) / 2
    const my = (y0 + y1) / 2
    path += ` Q${x0},${y0} ${mx},${my}`
  }
  const last = pts[pts.length - 1]
  path += ` L${last[0]},${last[1]}`
  return path
})

const areaPath = computed(() => {
  if (!linePath.value || !visible.value.length) return ''
  const d = visible.value
  const first = xScale(d[0].received_at)
  const last = xScale(d[d.length - 1].received_at)
  const floor = MARGIN.top + PLOT_H
  return `${linePath.value} L${last},${floor} L${first},${floor} Z`
})

// ─── Background zones ───────────────────────────────────────────
const zones = computed(() => {
  const { min, max } = yDomain.value
  const top = MARGIN.top
  const bottom = MARGIN.top + PLOT_H
  const hi = props.highThreshold
  const lo = props.lowThreshold
  const zonesList: { y: number; height: number; className: string }[] = []
  if (hi != null && hi < max) {
    const y = yScale(Math.min(hi, max))
    zonesList.push({ y: top, height: Math.max(y - top, 0), className: 'zone-high' })
  }
  if (lo != null && lo > min) {
    const y = yScale(Math.max(lo, min))
    zonesList.push({ y, height: Math.max(bottom - y, 0), className: 'zone-low' })
  }
  const normalTop = hi != null ? yScale(Math.min(hi, max)) : top
  const normalBottom = lo != null ? yScale(Math.max(lo, min)) : bottom
  if (normalBottom > normalTop) {
    zonesList.push({ y: normalTop, height: normalBottom - normalTop, className: 'zone-normal' })
  }
  return zonesList
})

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
const svgEl = ref<SVGSVGElement | null>(null)
const hoverIndex = ref<number | null>(null)
const hoveredMarker = ref<(typeof markers.value)[number] | null>(null)
const tooltipPos = ref({ x: 0, y: 0 })

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

// ─── Drag to pan ──────────────────────────────────────────────────
const dragging = ref(false)
const dragStartX = ref(0)
const dragStartZoom = ref({ start: 0, end: 1 })

function onPointerDown(e: PointerEvent) {
  hoveredMarker.value = null
  dragging.value = true
  dragStartX.value = e.clientX
  dragStartZoom.value = { start: zoomStart.value, end: zoomEnd.value }
  ;(e.target as Element).setPointerCapture?.(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  const pt = svgPoint(e.clientX, e.clientY)
  if (!pt) return

  if (dragging.value) {
    hoverIndex.value = null
    const dxFraction = (e.clientX - dragStartX.value) / (svgEl.value?.getBoundingClientRect().width || 1)
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
    return
  }

  if (pt.x < MARGIN.left || pt.x > VB_W - MARGIN.right) {
    hoverIndex.value = null
    return
  }
  hoverIndex.value = nearestIndex(pt.x)
  tooltipPos.value = pt
}

function onPointerUp(e: PointerEvent) {
  dragging.value = false
  ;(e.target as Element).releasePointerCapture?.(e.pointerId)
}

function onPointerLeave() {
  if (!dragging.value) hoverIndex.value = null
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
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

// ─── Touch: one-finger pan, two-finger pinch zoom ─────────────────
let touchStartDist = 0
let touchStartZoom = { start: 0, end: 1 }
let touchStartX = 0

function touchDist(t: TouchList): number {
  const [a, b] = [t[0], t[1]]
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
}

function onTouchStart(e: TouchEvent) {
  if (e.touches.length === 2) {
    touchStartDist = touchDist(e.touches)
    touchStartZoom = { start: zoomStart.value, end: zoomEnd.value }
  } else if (e.touches.length === 1) {
    touchStartX = e.touches[0].clientX
    touchStartZoom = { start: zoomStart.value, end: zoomEnd.value }
  }
}

function onTouchMove(e: TouchEvent) {
  if (e.touches.length === 2) {
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
  } else if (e.touches.length === 1) {
    e.preventDefault()
    const rect = svgEl.value?.getBoundingClientRect()
    if (!rect) return
    const dxFraction = (e.touches[0].clientX - touchStartX) / rect.width
    const window = touchStartZoom.end - touchStartZoom.start
    let newStart = touchStartZoom.start - dxFraction * window
    let newEnd = touchStartZoom.end - dxFraction * window
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
}

// ─── Tooltip content ──────────────────────────────────────────────
const hoveredReading = computed(() => (hoverIndex.value != null ? visible.value[hoverIndex.value] : null))

const alarmStatusAtHover = computed(() => {
  const r = hoveredReading.value
  if (!r) return null
  const t = new Date(r.received_at).getTime()
  const match = props.alarms.find((a) => {
    const s = new Date(a.triggered_at ?? a.detected_at).getTime()
    const e = a.resolved_at ? new Date(a.resolved_at).getTime() : Date.now()
    return t >= s && t <= e
  })
  return match ? alarmTypeLabel(match.alarm_type) : 'Normal'
})

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

const tooltipStyle = computed(() => positionFromViewBox(tooltipPos.value.x, tooltipPos.value.y))

const markerTooltipStyle = computed(() => {
  const m = hoveredMarker.value
  if (!m) return {}
  return positionFromViewBox(m.x1, STRIP_Y)
})
</script>

<template>
  <div class="temp-chart">
    <div class="chart-toolbar">
      <span class="trend" :class="`trend-${trend.dir}`">
        Trend <b>{{ trend.glyph }} {{ trend.label }}</b>
      </span>
      <button v-if="isZoomed" type="button" class="reset-zoom" @click="resetZoom">Reset zoom ↺</button>
    </div>

    <div v-if="loading" class="state-message">Ładowanie danych…</div>

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
          v-if="lowThreshold != null"
          :x1="MARGIN.left"
          :x2="VB_W - MARGIN.right"
          :y1="yScale(lowThreshold)"
          :y2="yScale(lowThreshold)"
          class="threshold-line threshold-low"
        />

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
          />
          <circle
            :cx="xScale(hoveredReading.received_at)"
            :cy="yScale(hoveredReading.temperature)"
            r="4.5"
            class="hover-dot"
          />
        </template>
      </svg>

      <!-- Point tooltip -->
      <div v-if="hoveredReading" class="tooltip" :style="tooltipStyle">
        <div class="tooltip-title">{{ sensor.name }}</div>
        <dl>
          <dt>Temperature</dt><dd>{{ fmtTemp(hoveredReading.temperature) }}</dd>
          <dt>Date</dt><dd>{{ fmtDate(hoveredReading.received_at) }}</dd>
          <dt>Time</dt><dd>{{ fmtTime(hoveredReading.received_at) }}</dd>
          <dt>Sensor status</dt><dd :class="{ 'status-bad': !online }">{{ online ? 'ONLINE' : 'OFFLINE' }}</dd>
          <dt>Alarm status</dt><dd :class="{ 'status-bad': alarmStatusAtHover !== 'Normal' }">{{ alarmStatusAtHover }}</dd>
          <dt>Last MQTT message</dt><dd>{{ sensor.last_message_at ? fmtTime(sensor.last_message_at) : '—' }}</dd>
        </dl>
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

.chart-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 20px;
  min-height: 28px;
}

.trend {
  font-size: 13px;
  color: #8fa1ba;
  display: flex;
  align-items: center;
  gap: 8px;
}
.trend b {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.trend-up b { color: #ff9f66; }
.trend-down b { color: #4ea8ff; }
.trend-flat b { color: #00e77b; }

.reset-zoom {
  margin-left: auto;
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
  margin-top: 14px;
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

.axis-label { fill: #9cadc7; font-size: 15px; }
.y-label { text-anchor: end; dominant-baseline: middle; }
.x-label { text-anchor: middle; }

.area-fill { fill: url(#area-gradient); opacity: 0.5; }
.line-path {
  fill: none;
  stroke: #0edbe5;
  stroke-width: 2.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.strip-baseline { stroke: #1a2f43; stroke-width: 1; vector-effect: non-scaling-stroke; }
.marker-span { stroke-width: 2; vector-effect: non-scaling-stroke; opacity: 0.6; }
.marker-glyph { font-size: 13px; text-anchor: middle; cursor: pointer; }
.marker-resolved { fill: #00e77b; cursor: pointer; }

.marker-high, .marker-high.marker-span { fill: #ff6875; stroke: #ff6875; }
.marker-low, .marker-low.marker-span { fill: #4ea8ff; stroke: #4ea8ff; }
.marker-offline, .marker-offline.marker-span { fill: #8fa1ba; stroke: #8fa1ba; }

.crosshair { stroke: #8fa1ba; stroke-width: 1; stroke-dasharray: 4 4; vector-effect: non-scaling-stroke; opacity: 0.6; }
.hover-dot { fill: #0edbe5; stroke: #071620; stroke-width: 2; vector-effect: non-scaling-stroke; }

.tooltip {
  position: absolute;
  z-index: 4;
  min-width: 200px;
  max-width: calc(100% - 12px);
  box-sizing: border-box;
  background: #0a1827;
  border: 1px solid #26516b;
  border-radius: 8px;
  padding: 12px 14px;
  pointer-events: none;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}
.tooltip-title { font-size: 13px; font-weight: 600; color: #00dde1; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.03em; }
.tooltip-title.marker-high { color: #ff6875; }
.tooltip-title.marker-low { color: #4ea8ff; }
.tooltip-title.marker-offline { color: #8fa1ba; }
.tooltip dl { display: grid; grid-template-columns: auto auto; gap: 4px 14px; margin: 0; }
.tooltip dt { font-size: 12px; color: #8fa1ba; }
.tooltip dd { margin: 0; font-size: 12px; color: #e8effa; text-align: right; font-variant-numeric: tabular-nums; }
.tooltip dd.status-bad { color: #ff6875; }

@media (max-width: 1100px) {
  .chart-toolbar { margin-top: 14px; }
}

@media (max-width: 800px) {
  .chart-wrap { margin-top: 10px; }
  .axis-label { font-size: 20px; }
  .tooltip { min-width: 170px; padding: 10px 12px; }
  .tooltip dt, .tooltip dd { font-size: 11px; }
}
</style>
