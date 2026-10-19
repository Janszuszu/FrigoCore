package pl.frigocore.service.ui.sensor

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
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
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.theme.FrigoCritical
import java.time.Instant
import java.time.ZoneId
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor

/** Rounded y-axis bounds with a little headroom, so a flat line still has
 * visible scale and labels land on whole degrees. */
internal fun axisBounds(min: Double, max: Double): Pair<Double, Double> {
    val span = (max - min).coerceAtLeast(2.0)
    val pad = span * 0.1
    return floor(min - pad) to ceil(max + pad)
}

/** Fixed value axis around the normal-work band [low, high] (the sensor's
 * alarm thresholds), so paging between days never rescales the chart.
 * Null when the band is not fully defined; the chart then fits the data. */
internal fun normalBandBounds(low: Double?, high: Double?): Pair<Double, Double>? {
    if (low == null || high == null || high <= low) return null
    val pad = ((high - low) * 0.25).coerceAtLeast(2.0)
    return floor(low - pad) to ceil(high + pad)
}

private enum class Gesture { TAP, SWIPE }

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
 * axis, labelled with [xLabels] (start, middle, end), [yBounds] the value axis; readings outside
 * [yBounds] run off the plot edge. [limits] are drawn as dashed alarm lines.
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

    Canvas(
        modifier = modifier
            .pointerInput(points, onSwipePage) {
                val pageDistance = 60.dp.toPx()
                awaitEachGesture {
                    val down = awaitFirstDown()
                    val slop = viewConfiguration.touchSlop
                    // Up before the long-press timeout = tap, sideways past slop = swipe,
                    // neither = long press, which scrubs.
                    var gesture: Gesture? = null
                    withTimeoutOrNull(viewConfiguration.longPressTimeoutMillis) {
                        while (gesture == null) {
                            val change = awaitPointerEvent().changes.firstOrNull { it.id == down.id }
                            if (change == null || !change.pressed) gesture = Gesture.TAP
                            else if (abs(change.position.x - down.position.x) > slop) gesture = Gesture.SWIPE
                        }
                    }
                    if (gesture == Gesture.TAP) {
                        selectedX = down.position.x
                        return@awaitEachGesture
                    }
                    val swipe = gesture == Gesture.SWIPE && onSwipePage != null
                    if (!swipe) selectedX = down.position.x
                    var lastX = down.position.x
                    while (true) {
                        val change = awaitPointerEvent().changes.firstOrNull { it.id == down.id } ?: break
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

        val (yMin, yMax) = yBounds ?: axisBounds(points.minOf { it.value }, points.maxOf { it.value })
        val tStart = window?.first?.toEpochMilli() ?: points.first().time.toEpochMilli()
        val tEnd = window?.second?.toEpochMilli() ?: points.last().time.toEpochMilli()
        val tSpan = (tEnd - tStart).coerceAtLeast(1).toFloat()
        fun x(p: ChartPoint) = leftPad + (p.time.toEpochMilli() - tStart) / tSpan * chartW
        fun y(v: Double) = topPad + ((yMax - v) / (yMax - yMin)).toFloat() * chartH

        // Horizontal grid + y labels
        val steps = 4
        for (i in 0..steps) {
            val v = yMin + (yMax - yMin) * i / steps
            val yy = y(v)
            drawLine(gridColor, Offset(leftPad, yy), Offset(size.width, yy), 1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
            val label = textMeasurer.measure(String.format(java.util.Locale.ROOT, if (unit == "°C") "%.0f°" else "%.0f", v), labelStyle)
            drawText(label, topLeft = Offset(leftPad - label.size.width - 6.dp.toPx(), yy - label.size.height / 2))
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
