package pl.frigocore.service.ui.sensor

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.frigocore.service.ui.common.Formatters
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

/** Line chart of temperature over time; touch or drag to read a value.
 * Fills whatever size [modifier] gives it. */
@Composable
fun TemperatureChart(points: List<ChartPoint>, showDates: Boolean, modifier: Modifier = Modifier) {
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
            .pointerInput(points) {
                detectTapGestures { selectedX = it.x }
            }
            .pointerInput(points) {
                detectDragGestures(onDragEnd = { selectedX = null }) { change, _ -> selectedX = change.position.x }
            },
    ) {
        if (points.size < 2) return@Canvas
        val leftPad = 44.dp.toPx()
        val bottomPad = 22.dp.toPx()
        val topPad = 8.dp.toPx()
        val chartW = size.width - leftPad
        val chartH = size.height - bottomPad - topPad

        val (yMin, yMax) = axisBounds(points.minOf { it.value }, points.maxOf { it.value })
        val tStart = points.first().time.toEpochMilli()
        val tEnd = points.last().time.toEpochMilli()
        val tSpan = (tEnd - tStart).coerceAtLeast(1).toFloat()
        fun x(p: ChartPoint) = leftPad + (p.time.toEpochMilli() - tStart) / tSpan * chartW
        fun y(v: Double) = topPad + ((yMax - v) / (yMax - yMin)).toFloat() * chartH

        // Horizontal grid + y labels
        val steps = 4
        for (i in 0..steps) {
            val v = yMin + (yMax - yMin) * i / steps
            val yy = y(v)
            drawLine(gridColor, Offset(leftPad, yy), Offset(size.width, yy), 1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
            val label = textMeasurer.measure(String.format(java.util.Locale.ROOT, "%.0f°", v), labelStyle)
            drawText(label, topLeft = Offset(leftPad - label.size.width - 6.dp.toPx(), yy - label.size.height / 2))
        }

        // X labels: start, middle, end
        listOf(0f, 0.5f, 1f).forEach { f ->
            val instant = java.time.Instant.ofEpochMilli(tStart + (tSpan * f).toLong())
            val text = if (showDates) "${Formatters.shortDate(instant)} ${Formatters.time(instant)}" else Formatters.time(instant)
            val label = textMeasurer.measure(text, labelStyle)
            val lx = (leftPad + chartW * f - label.size.width * f).coerceIn(leftPad, size.width - label.size.width)
            drawText(label, topLeft = Offset(lx, size.height - label.size.height))
        }

        // Line + soft fill
        val line = Path()
        points.forEachIndexed { i, p -> if (i == 0) line.moveTo(x(p), y(p.value)) else line.lineTo(x(p), y(p.value)) }
        val fill = Path().apply {
            addPath(line)
            lineTo(x(points.last()), topPad + chartH)
            lineTo(x(points.first()), topPad + chartH)
            close()
        }
        drawPath(fill, Brush.verticalGradient(listOf(lineColor.copy(alpha = 0.25f), lineColor.copy(alpha = 0f)), topPad, topPad + chartH))
        drawPath(line, lineColor, style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))

        // Selected point tooltip
        selectedX?.let { sx ->
            val nearest = points.minBy { abs(x(it) - sx) }
            val px = x(nearest)
            val py = y(nearest.value)
            drawLine(labelColor, Offset(px, topPad), Offset(px, topPad + chartH), 1f)
            drawCircle(lineColor, 5.dp.toPx(), Offset(px, py))
            val text = "${Formatters.temperature(nearest.value)} · ${Formatters.shortDate(nearest.time)} ${Formatters.time(nearest.time)}"
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
