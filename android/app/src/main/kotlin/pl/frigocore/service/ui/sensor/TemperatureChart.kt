package pl.frigocore.service.ui.sensor

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.input.pointer.AwaitPointerEventScope
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoWarning
import java.time.Instant
import java.time.ZoneId
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.pow
import kotlin.math.hypot

/** Rounded y-axis bounds with a little headroom, so a flat line still has
 * visible scale and labels land on whole degrees. */
internal fun axisBounds(min: Double, max: Double): Pair<Double, Double> {
    val span = (max - min).coerceAtLeast(2.0)
    val pad = span * 0.1
    return floor(min - pad) to ceil(max + pad)
}

/** Value axis widened to whole steps of 1, 2 or 5 (times a power of ten)
 * giving at most five intervals, e.g. 1.9..18.3 reads 0..20 every 5.
 * Returns (low, high, step). */
internal fun niceAxis(min: Double, max: Double, minStep: Double = 1.0): Triple<Double, Double, Double> {
    val raw = ((max - min) / 5).coerceAtLeast(1e-9)
    val magnitude = 10.0.pow(floor(log10(raw)))
    val step = listOf(1.0, 2.0, 5.0, 10.0).map { it * magnitude }.first { it >= raw }.coerceAtLeast(minStep)
    return Triple(floor(min / step) * step, ceil(max / step) * step, step)
}

/** Fixed value axis around the normal-work band [low, high] (the sensor's
 * alarm thresholds), so paging between days never rescales the chart.
 * Null when the band is not fully defined; the chart then fits the data. */
internal fun normalBandBounds(low: Double?, high: Double?): Pair<Double, Double>? {
    if (low == null || high == null || high <= low) return null
    val pad = ((high - low) * 0.25).coerceAtLeast(2.0)
    return floor(low - pad) to ceil(high + pad)
}

/** Narrowest and widest value span a pinch can reach, in the sensor's unit. */
private const val MIN_ZOOM_SPAN = 1.0
private const val MAX_ZOOM_SPAN = 200.0

/** Value range after a pinch that started on the range [max0 - span0, max0]:
 * the span divided by [factor] (> 1 zooms in), and the value that sat under
 * the fingers' midpoint at [focalFrac0] (0 = top edge, 1 = bottom) now sits
 * at [focalFracNow], so the view follows the fingers. Returns (min, max). */
internal fun pinchRange(max0: Double, span0: Double, focalFrac0: Float, focalFracNow: Float, factor: Float): Pair<Double, Double> {
    val focalValue = max0 - focalFrac0 * span0
    val span = (span0 / factor).coerceIn(MIN_ZOOM_SPAN, MAX_ZOOM_SPAN)
    val max = focalValue + focalFracNow * span
    return (max - span) to max
}

/** The value axis as last drawn, read by the gesture handler. */
private class AxisFrame(var max: Double = 1.0, var span: Double = 1.0, var top: Float = 0f, var height: Float = 1f)

private enum class Gesture { TAP, SWIPE, PAN, PINCH }

/** Two-finger pinch on the value axis until fewer than two fingers remain. */
private suspend fun AwaitPointerEventScope.trackPinch(frame: AxisFrame, onZoom: (Pair<Double, Double>) -> Unit) {
    val max0 = frame.max
    val span0 = frame.span
    var start: Pair<Float, Float>? = null
    while (true) {
        val event = awaitPointerEvent()
        val pressed = event.changes.filter { it.pressed }
        if (pressed.size < 2) break
        val (a, b) = pressed[0].position to pressed[1].position
        val distance = hypot(a.x - b.x, a.y - b.y).coerceAtLeast(24f)
        val frac = ((a.y + b.y) / 2 - frame.top) / frame.height
        val (frac0, distance0) = start ?: (frac to distance).also { start = it }
        onZoom(pinchRange(max0, span0, frac0, frac, distance / distance0))
        event.changes.forEach { it.consume() }
    }
}

/** Bottom-axis labels at the start, middle and end of a page: minutes
 * 00 / 30 / 60 for an hour, clock times otherwise, with the closing
 * midnight written 24:00. */
internal fun pageAxisLabels(range: HistoryRange, window: Pair<Instant, Instant>, zone: ZoneId = ZoneId.systemDefault()): List<String> {
    if (range == HistoryRange.H1) return listOf("00", "30", "60")
    val (start, end) = window
    val mid = Instant.ofEpochMilli((start.toEpochMilli() + end.toEpochMilli()) / 2)
    val endLabel = Formatters.time(end, zone).let { if (it == "00:00") "24:00" else it }
    return listOf(Formatters.time(start, zone), Formatters.time(mid, zone), endLabel)
}

/** Line chart of temperature over time. Tap to read a value; long-press and
 * drag to scrub. With [onSwipePage], a horizontal drag pages the window
 * (left = +1, right = -1); without it any drag scrubs. [window] pins the time
 * axis, labelled with [xLabels] (start, middle, end), [yBounds] the value axis.
 * Two fingers zoom the value axis only ([yZoom], reported via [onYZoom]); while
 * zoomed a vertical drag pans it, and a double tap returns to the default
 * scale. Readings outside the shown range run off the plot and get a small
 * marker at that edge. [limits] are drawn as dashed alarm lines.
 * Fills whatever size [modifier] gives it. */
@Composable
fun TemperatureChart(
    points: List<ChartPoint>,
    showDates: Boolean,
    unit: String = "°C",
    window: Pair<Instant, Instant>? = null,
    xLabels: List<String>? = null,
    yBounds: Pair<Double, Double>? = null,
    limits: List<Double> = emptyList(),
    onSwipePage: ((Int) -> Unit)? = null,
    yZoom: Pair<Double, Double>? = null,
    onYZoom: (Pair<Double, Double>?) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val lineColor = MaterialTheme.colorScheme.primary
    val gridColor = MaterialTheme.colorScheme.outlineVariant
    val labelColor = MaterialTheme.colorScheme.onSurfaceVariant
    val tooltipColor = MaterialTheme.colorScheme.inverseSurface
    val tooltipText = MaterialTheme.colorScheme.inverseOnSurface
    val textMeasurer = rememberTextMeasurer()
    val labelStyle = TextStyle(fontSize = 11.sp, color = labelColor)
    var selectedX by remember(points) { mutableStateOf<Float?>(null) }
    val frame = remember { AxisFrame() }
    val zoomed = rememberUpdatedState(yZoom != null)
    val setZoom = rememberUpdatedState(onYZoom)
    // Uptime and x of the last single tap, to spot a double tap.
    val lastTap = remember { floatArrayOf(-1e9f, 0f) }

    Canvas(
        modifier = modifier
            .pointerInput(points, onSwipePage) {
                val pageDistance = 60.dp.toPx()
                val zoomTo: (Pair<Double, Double>) -> Unit = { setZoom.value(it) }
                awaitEachGesture {
                    val down = awaitFirstDown()
                    val slop = viewConfiguration.touchSlop
                    // Second finger = pinch, up before the long-press timeout = tap,
                    // sideways past slop = swipe, upright past slop while zoomed = pan,
                    // none of these = long press, which scrubs.
                    var gesture: Gesture? = null
                    withTimeoutOrNull(viewConfiguration.longPressTimeoutMillis) {
                        while (gesture == null) {
                            val event = awaitPointerEvent()
                            val change = event.changes.firstOrNull { it.id == down.id }
                            val dx = abs((change?.position?.x ?: 0f) - down.position.x)
                            val dy = abs((change?.position?.y ?: 0f) - down.position.y)
                            gesture = when {
                                event.changes.count { it.pressed } >= 2 -> Gesture.PINCH
                                change == null || !change.pressed -> Gesture.TAP
                                dx > slop && dx >= dy -> Gesture.SWIPE
                                dy > slop && zoomed.value -> Gesture.PAN
                                else -> null
                            }
                        }
                    }
                    when (gesture) {
                        Gesture.TAP -> {
                            val now = down.uptimeMillis.toFloat()
                            val double = now - lastTap[0] < viewConfiguration.doubleTapTimeoutMillis &&
                                abs(down.position.x - lastTap[1]) < 48.dp.toPx()
                            if (double) {
                                setZoom.value(null)
                                selectedX = null
                                lastTap[0] = -1e9f
                            } else {
                                selectedX = down.position.x
                                lastTap[0] = now
                                lastTap[1] = down.position.x
                            }
                            return@awaitEachGesture
                        }
                        Gesture.PINCH -> {
                            selectedX = null
                            trackPinch(frame, zoomTo)
                            return@awaitEachGesture
                        }
                        Gesture.PAN -> {
                            val max0 = frame.max
                            val span0 = frame.span
                            while (true) {
                                val event = awaitPointerEvent()
                                if (event.changes.count { it.pressed } >= 2) {
                                    trackPinch(frame, zoomTo)
                                    break
                                }
                                val change = event.changes.firstOrNull { it.id == down.id } ?: break
                                if (!change.pressed) break
                                // The curve follows the finger: dragging down shows higher values.
                                val shift = (change.position.y - down.position.y) / frame.height * span0
                                zoomTo((max0 + shift - span0) to (max0 + shift))
                                change.consume()
                            }
                            return@awaitEachGesture
                        }
                        else -> Unit
                    }
                    val swipe = gesture == Gesture.SWIPE && onSwipePage != null
                    if (!swipe) selectedX = down.position.x
                    var lastX = down.position.x
                    while (true) {
                        val event = awaitPointerEvent()
                        if (event.changes.count { it.pressed } >= 2) {
                            selectedX = null
                            trackPinch(frame, zoomTo)
                            return@awaitEachGesture
                        }
                        val change = event.changes.firstOrNull { it.id == down.id } ?: break
                        if (!change.pressed) break
                        lastX = change.position.x
                        if (!swipe) selectedX = lastX
                        change.consume()
                    }
                    if (swipe) {
                        val dx = lastX - down.position.x
                        if (dx <= -pageDistance) onSwipePage?.invoke(1)
                        else if (dx >= pageDistance) onSwipePage?.invoke(-1)
                    } else {
                        selectedX = null
                    }
                }
            },
    ) {
        if (points.size < 2) return@Canvas
        val leftPad = 44.dp.toPx()
        val bottomPad = 22.dp.toPx()
        val topPad = 8.dp.toPx()
        val chartW = size.width - leftPad
        val chartH = size.height - bottomPad - topPad

        val (rawMin, rawMax) = yBounds ?: axisBounds(points.minOf { it.value }, points.maxOf { it.value })
        // A pinch shows exactly the chosen range, ticked at round values inside it;
        // the default scale snaps its ends to round values.
        val (yMin, yMax, yStep) = yZoom?.let { (lo, hi) -> Triple(lo, hi, niceAxis(lo, hi, minStep = 0.1).third) }
            ?: niceAxis(rawMin, rawMax)
        frame.max = yMax
        frame.span = yMax - yMin
        frame.top = topPad
        frame.height = chartH
        val tStart = window?.first?.toEpochMilli() ?: points.first().time.toEpochMilli()
        val tEnd = window?.second?.toEpochMilli() ?: points.last().time.toEpochMilli()
        val tSpan = (tEnd - tStart).coerceAtLeast(1).toFloat()
        fun x(p: ChartPoint) = leftPad + (p.time.toEpochMilli() - tStart) / tSpan * chartW
        fun y(v: Double) = topPad + ((yMax - v) / (yMax - yMin)).toFloat() * chartH

        // Horizontal grid + y labels
        val decimals = if (yStep < 1.0) 1 else 0
        val epsilon = yStep * 1e-6
        var v = ceil(yMin / yStep - 1e-6) * yStep
        while (v <= yMax + epsilon) {
            val yy = y(v)
            drawLine(gridColor, Offset(leftPad, yy), Offset(size.width, yy), 1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
            val text = String.format(java.util.Locale.ROOT, "%.${decimals}f", v) + if (unit == "°C") "°" else ""
            val label = textMeasurer.measure(text, labelStyle)
            drawText(label, topLeft = Offset(leftPad - label.size.width - 6.dp.toPx(), yy - label.size.height / 2))
            v += yStep
        }

        // X labels: start, middle, end
        val labels = xLabels ?: listOf(0f, 0.5f, 1f).map { f ->
            val instant = Instant.ofEpochMilli(tStart + (tSpan * f).toLong())
            if (showDates) "${Formatters.shortDate(instant)} ${Formatters.time(instant)}" else Formatters.time(instant)
        }
        listOf(0f, 0.5f, 1f).zip(labels).forEach { (f, text) ->
            val label = textMeasurer.measure(text, labelStyle)
            val lx = (leftPad + chartW * f - label.size.width * f).coerceIn(leftPad, size.width - label.size.width)
            drawText(label, topLeft = Offset(lx, size.height - label.size.height))
            if (window != null && f > 0f) {
                val gx = leftPad + chartW * f
                drawLine(gridColor, Offset(gx, topPad), Offset(gx, topPad + chartH), 1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
            }
        }

        // Alarm thresholds
        limits.filter { it in yMin..yMax }.forEach { v ->
            drawLine(FrigoCritical.copy(alpha = 0.7f), Offset(leftPad, y(v)), Offset(size.width, y(v)), 1.5f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 6f)))
        }

        // Line + soft fill
        val line = Path()
        // Step line: hold each reading level until the next one, then jump.
        points.forEachIndexed { i, p ->
            if (i == 0) line.moveTo(x(p), y(p.value))
            else {
                line.lineTo(x(p), y(points[i - 1].value))
                line.lineTo(x(p), y(p.value))
            }
        }
        val fill = Path().apply {
            addPath(line)
            lineTo(x(points.last()), topPad + chartH)
            lineTo(x(points.first()), topPad + chartH)
            close()
        }
        clipRect(leftPad, topPad, size.width, topPad + chartH) {
            drawPath(fill, Brush.verticalGradient(listOf(lineColor.copy(alpha = 0.25f), lineColor.copy(alpha = 0f)), topPad, topPad + chartH))
            drawPath(line, lineColor, style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Butt, join = StrokeJoin.Miter))
        }

        // Readings beyond the shown range: a small triangle at that edge, at most one per 8 dp.
        val marker = 5.dp.toPx()
        var lastMarkerX = Float.NEGATIVE_INFINITY
        points.forEach { p ->
            val above = p.value > yMax
            if (!above && p.value >= yMin) return@forEach
            val px = x(p)
            if (px - lastMarkerX < 8.dp.toPx()) return@forEach
            lastMarkerX = px
            val edge = if (above) topPad else topPad + chartH
            val base = if (above) edge + marker * 1.4f else edge - marker * 1.4f
            val triangle = Path().apply {
                moveTo(px, edge)
                lineTo(px - marker, base)
                lineTo(px + marker, base)
                close()
            }
            drawPath(triangle, FrigoWarning.copy(alpha = 0.85f))
        }

        // Selected point tooltip
        selectedX?.let { sx ->
            val nearest = points.minBy { abs(x(it) - sx) }
            val px = x(nearest)
            val py = y(nearest.value).coerceIn(topPad, topPad + chartH)
            drawLine(labelColor, Offset(px, topPad), Offset(px, topPad + chartH), 1f)
            drawCircle(lineColor, 5.dp.toPx(), Offset(px, py))
            val text = "${Formatters.reading(nearest.value, unit)} · ${Formatters.shortDate(nearest.time)} ${Formatters.time(nearest.time)}"
            val label = textMeasurer.measure(text, TextStyle(fontSize = 12.sp, color = tooltipText))
            val boxW = label.size.width + 16.dp.toPx()
            val boxH = label.size.height + 8.dp.toPx()
            val bx = (px - boxW / 2).coerceIn(leftPad, size.width - boxW)
            val by = (py - boxH - 10.dp.toPx()).coerceAtLeast(0f)
            drawRoundRect(tooltipColor, Offset(bx, by), Size(boxW, boxH), CornerRadius(6.dp.toPx()))
            drawText(label, topLeft = Offset(bx + 8.dp.toPx(), by + 4.dp.toPx()))
        }
    }
}
