package pl.frigocore.service.ui.aggregates

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.outlined.AcUnit
import androidx.compose.material.icons.outlined.HomeWork
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.quietClickable
import pl.frigocore.service.ui.theme.Barlow
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoBackground
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoMax
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoSurfaceHigh
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import java.text.Normalizer

/** The aggregate's sensors that have a place on the refrigeration-cycle
 * diagram, found by name (and kind for the electrical ones). */
data class CycleSensors(
    val discharge: SensorResponse,
    val suction: SensorResponse,
    val condenser: SensorResponse,
    val compressor: SensorResponse?,
    val outdoor: SensorResponse?,
    val current: SensorResponse?,
    val power: SensorResponse?,
)

private fun plain(text: String): String =
    Normalizer.normalize(text.lowercase().replace('ł', 'l'), Normalizer.Form.NFD).replace(Regex("\\p{M}"), "")

/** The diagram needs the discharge, suction and condenser lines and the
 * aggregate's electrical meter (current or power); an aggregate without
 * them (Biskupiec: only outdoor, discharge and suction) gets just the
 * sensor rows. Names are matched loosely: "Agregat — tłoczenie",
 * "Chłodnia/Pchanie", "Ssanie", "skraplacz", "sprężarka", "zewnętrzna". */
internal fun cycleSensors(sensors: List<SensorResponse>): CycleSensors? {
    fun temp(vararg keys: String) = sensors.firstOrNull { s ->
        s.kind == "temperature" && keys.any { it in plain(s.name) }
    }
    val discharge = temp("tlocz", "pchan", "discharge") ?: return null
    val suction = temp("ssani", "ssan", "suction") ?: return null
    val condenser = temp("skrapl", "condens") ?: return null
    val current = sensors.firstOrNull { it.kind == "current" }
    val power = sensors.firstOrNull { it.kind == "power" }
    if (current == null && power == null) return null
    return CycleSensors(
        discharge = discharge,
        suction = suction,
        condenser = condenser,
        compressor = temp("sprezark", "kompresor", "compressor"),
        outdoor = temp("zewn", "outdoor"),
        current = current,
        power = power,
    )
}

private val Liquid = Color(0xFFFFC21A)
private val Steel = Color(0xFF2A3A52)

private val LabelStyle = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 14.sp, letterSpacing = 0.5.sp)
private val ValueStyle = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.SemiBold, fontSize = 26.sp, fontFeatureSettings = "tnum")

private fun reading(sensor: SensorResponse?): String =
    sensor?.let { Formatters.reading(it.current_temperature, it.unit) } ?: "—"

/** The refrigeration cycle as a picture: compressor on top with the
 * discharge (red) and suction (blue) lines, condenser bottom left, the
 * liquid line (yellow) across to the receivers bottom right, each with its
 * reading; under it the outdoor temperature, current and power. Tapping a
 * reading opens its chart. */
@Composable
internal fun AggregateDiagram(cycle: CycleSensors, onOpenChart: (SensorResponse) -> Unit) {
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, FrigoAccent.copy(alpha = 0.25f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth(),
    ) {
        BoxWithConstraints(Modifier.fillMaxWidth().aspectRatio(1f / 0.86f).padding(8.dp)) {
            val w = maxWidth
            val h = maxHeight
            Canvas(Modifier.fillMaxSize()) { drawCycle() }
            // Fan discs: sun on the condenser, snowflake on the receivers.
            Icon(
                Icons.Outlined.WbSunny, contentDescription = null, tint = Liquid,
                modifier = Modifier.centeredAt(w * 0.2f, h * 0.74f, 34.dp),
            )
            Icon(
                Icons.Outlined.AcUnit, contentDescription = null, tint = FrigoAccent,
                modifier = Modifier.centeredAt(w * 0.8f, h * 0.74f, 34.dp),
            )
            Reading("TŁOCZENIE", reading(cycle.discharge), FrigoCritical, w * 0.27f, h * 0.02f) { onOpenChart(cycle.discharge) }
            Reading("SSANIE", reading(cycle.suction), FrigoAccent, w * 0.73f, h * 0.02f) { onOpenChart(cycle.suction) }
            Reading("SPRĘŻARKA", reading(cycle.compressor), FrigoCritical, w * 0.5f, h * 0.36f) {
                cycle.compressor?.let(onOpenChart)
            }
            Reading("SKRAPLACZ", reading(cycle.condenser), Liquid, w * 0.2f, h * 0.87f) { onOpenChart(cycle.condenser) }
            Reading("ODBIORNIKI", null, FrigoText, w * 0.8f, h * 0.87f) {}
        }
        ElectricRow(cycle, onOpenChart)
    }
}

/** Places a composable with its centre at ([x], [y]) inside the diagram box. */
private fun Modifier.centeredAt(x: Dp, y: Dp, size: Dp): Modifier =
    this.offset(x - size / 2, y - size / 2).size(size)

/** A label over its value, centred on [x] with its top at [y]. */
@Composable
private fun Reading(label: String, value: String?, color: Color, x: Dp, y: Dp, onClick: () -> Unit) {
    Layout(
        content = {
            Column(Modifier.quietClickable(onClick), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(label, color = if (value == null) FrigoText else FrigoTextMuted.copy(alpha = 0.95f), style = LabelStyle)
                if (value != null) Text(value, color = color, style = ValueStyle)
            }
        },
    ) { measurables, constraints ->
        val p = measurables.first().measure(constraints.copy(minWidth = 0, minHeight = 0))
        layout(constraints.maxWidth, constraints.maxHeight) {
            p.place((x.roundToPx() - p.width / 2).coerceIn(0, (constraints.maxWidth - p.width).coerceAtLeast(0)), y.roundToPx())
        }
    }
}

private fun DrawScope.drawCycle() {
    val w = size.width
    val h = size.height
    val pipe = 7.dp.toPx()
    val radius = 22.dp.toPx()
    val topY = h * 0.25f
    val unitTop = h * 0.62f
    val leftX = w * 0.12f
    val rightX = w * 0.88f
    val compLeft = w * 0.42f
    val compRight = w * 0.58f

    fun line(color: Color, pts: List<Offset>) {
        val path = Path().apply {
            moveTo(pts[0].x, pts[0].y)
            for (i in 1 until pts.size) lineTo(pts[i].x, pts[i].y)
        }
        drawPath(
            path, color,
            style = Stroke(width = pipe, cap = StrokeCap.Round, join = StrokeJoin.Round, pathEffect = androidx.compose.ui.graphics.PathEffect.cornerPathEffect(radius)),
        )
    }
    // Discharge: compressor → down into the condenser. Suction: receivers → compressor.
    line(FrigoCritical, listOf(Offset(compLeft, topY), Offset(leftX, topY), Offset(leftX, unitTop)))
    line(FrigoAccent, listOf(Offset(rightX, unitTop), Offset(rightX, topY), Offset(compRight, topY)))
    // Liquid line across the bottom.
    line(Liquid, listOf(Offset(w * 0.33f, h * 0.74f), Offset(w * 0.67f, h * 0.74f)))

    val a = 9.dp.toPx()
    arrow(Offset(w * 0.3f, topY - 14.dp.toPx()), Offset(-1f, 0f), FrigoCritical, a)
    arrow(Offset(leftX - 14.dp.toPx(), h * 0.43f), Offset(0f, 1f), FrigoCritical, a)
    arrow(Offset(w * 0.7f, topY - 14.dp.toPx()), Offset(-1f, 0f), FrigoAccent, a)
    arrow(Offset(w * 0.5f, h * 0.74f + 16.dp.toPx()), Offset(1f, 0f), Liquid, a)
    // Air through the coils: in from the left, chilled out to the right.
    for (dy in listOf(-1, 0, 1)) {
        arrow(Offset(w * 0.035f, h * 0.74f + dy * 16.dp.toPx()), Offset(1f, 0f), FrigoCritical, a * 0.8f)
        arrow(Offset(w * 0.965f, h * 0.74f + dy * 16.dp.toPx()), Offset(1f, 0f), FrigoAccent, a * 0.8f)
    }

    coil(Offset(w * 0.2f, h * 0.74f), Size(w * 0.26f, h * 0.24f))
    coil(Offset(w * 0.8f, h * 0.74f), Size(w * 0.26f, h * 0.24f))
    compressor(Offset(w * 0.5f, topY), w * 0.17f)
}

/** A short shaft with a filled head pointing along [dir]. */
private fun DrawScope.arrow(at: Offset, dir: Offset, color: Color, len: Float) {
    val tail = at - dir * len
    drawLine(color, tail, at, strokeWidth = 3.dp.toPx(), cap = StrokeCap.Round)
    val n = Offset(-dir.y, dir.x)
    val head = Path().apply {
        moveTo(at.x + dir.x * len * 0.5f, at.y + dir.y * len * 0.5f)
        lineTo(at.x + n.x * len * 0.45f, at.y + n.y * len * 0.45f)
        lineTo(at.x - n.x * len * 0.45f, at.y - n.y * len * 0.45f)
        close()
    }
    drawPath(head, color)
}

/** Finned coil block with a fan disc in the middle. */
private fun DrawScope.coil(center: Offset, s: Size) {
    val topLeft = Offset(center.x - s.width / 2, center.y - s.height / 2)
    drawRoundRect(FrigoSurfaceHigh, topLeft, s, CornerRadius(4.dp.toPx()))
    val fins = 9
    for (i in 1 until fins) {
        val y = topLeft.y + s.height * i / fins
        drawLine(Steel, Offset(topLeft.x + 6.dp.toPx(), y), Offset(topLeft.x + s.width - 6.dp.toPx(), y), 1.5.dp.toPx())
    }
    drawRoundRect(Color(0xFF6B7C95), topLeft, s, CornerRadius(4.dp.toPx()), style = Stroke(2.dp.toPx()))
    // Side frames.
    for (x in listOf(topLeft.x, topLeft.x + s.width)) {
        drawLine(Color(0xFF8FA0B8), Offset(x, topLeft.y - 3.dp.toPx()), Offset(x, topLeft.y + s.height + 3.dp.toPx()), 3.dp.toPx())
    }
    val r = s.height * 0.36f
    drawCircle(FrigoBackground, r, center)
    drawCircle(Steel, r, center, style = Stroke(2.dp.toPx()))
}

/** Hermetic compressor: a shell with a domed top, a terminal box and feet. */
private fun DrawScope.compressor(center: Offset, width: Float) {
    val bodyH = width * 0.95f
    val top = center.y - bodyH * 0.55f
    val left = center.x - width / 2
    val shell = Color(0xFF16263B)
    val rim = Color(0xFF7F95B4)
    // Feet.
    drawLine(rim, Offset(left - 4.dp.toPx(), top + bodyH + 4.dp.toPx()), Offset(left + width + 4.dp.toPx(), top + bodyH + 4.dp.toPx()), 3.dp.toPx(), cap = StrokeCap.Round)
    // Shell and dome.
    drawRoundRect(shell, Offset(left, top + width * 0.18f), Size(width, bodyH - width * 0.18f), CornerRadius(width * 0.18f))
    drawRoundRect(rim, Offset(left, top + width * 0.18f), Size(width, bodyH - width * 0.18f), CornerRadius(width * 0.18f), style = Stroke(2.dp.toPx()))
    drawOval(shell, Offset(left + width * 0.04f, top), Size(width * 0.92f, width * 0.42f))
    drawOval(rim, Offset(left + width * 0.04f, top), Size(width * 0.92f, width * 0.42f), style = Stroke(2.dp.toPx()))
    // Highlight and seam.
    drawLine(Color.White.copy(alpha = 0.25f), Offset(left + width * 0.2f, top + width * 0.35f), Offset(left + width * 0.2f, top + bodyH * 0.8f), 3.dp.toPx(), cap = StrokeCap.Round)
    drawLine(rim.copy(alpha = 0.7f), Offset(left, top + bodyH * 0.45f), Offset(left + width, top + bodyH * 0.45f), 1.5.dp.toPx())
    // Terminal box on the suction side.
    val box = Size(width * 0.34f, bodyH * 0.42f)
    val boxTopLeft = Offset(left + width * 0.82f, center.y - box.height / 2)
    drawRoundRect(Color(0xFF1C2E47), boxTopLeft, box, CornerRadius(3.dp.toPx()))
    drawRoundRect(rim, boxTopLeft, box, CornerRadius(3.dp.toPx()), style = Stroke(1.5.dp.toPx()))
    for (i in 1..3) {
        val y = boxTopLeft.y + box.height * i / 4
        drawLine(rim, Offset(boxTopLeft.x + 3.dp.toPx(), y), Offset(boxTopLeft.x + box.width - 3.dp.toPx(), y), 1.dp.toPx())
    }
    // Discharge stub on the left.
    drawRoundRect(FrigoCritical.copy(alpha = 0.8f), Offset(left - 6.dp.toPx(), center.y - 6.dp.toPx()), Size(8.dp.toPx(), 12.dp.toPx()), CornerRadius(2.dp.toPx()))
}

/** Outdoor temperature, current and power side by side. */
@Composable
private fun ElectricRow(cycle: CycleSensors, onOpenChart: (SensorResponse) -> Unit) {
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, FrigoOutline),
        colors = CardDefaults.cardColors(containerColor = FrigoBackground.copy(alpha = 0.4f), contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth().padding(start = 10.dp, end = 10.dp, bottom = 10.dp),
    ) {
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min).padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Row(
                Modifier.weight(1.25f).quietClickable { cycle.outdoor?.let(onOpenChart) }.padding(start = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Outlined.HomeWork, contentDescription = null, tint = Color(0xFFC9D3E3), modifier = Modifier.size(34.dp))
                Spacer(Modifier.width(8.dp))
                Column {
                    Text("TEMP. ZEWNĘTRZNA", color = FrigoTextMuted, style = LabelStyle.copy(fontSize = 12.sp), maxLines = 1)
                    Text(reading(cycle.outdoor), color = FrigoAccent, style = ValueStyle.copy(fontSize = 24.sp), maxLines = 1)
                }
            }
            Box(Modifier.width(1.dp).fillMaxHeight().background(FrigoAccent.copy(alpha = 0.3f)))
            Row(
                Modifier.weight(1f).quietClickable { cycle.current?.let(onOpenChart) }.padding(start = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Filled.Bolt, contentDescription = null, tint = Liquid, modifier = Modifier.size(30.dp))
                Spacer(Modifier.width(4.dp))
                Column {
                    Text("PRĄD", color = FrigoTextMuted, style = LabelStyle.copy(fontSize = 12.sp), maxLines = 1)
                    Text(reading(cycle.current), color = FrigoMax, style = ValueStyle.copy(fontSize = 24.sp), maxLines = 1)
                }
            }
            Box(Modifier.width(1.dp).fillMaxHeight().background(FrigoAccent.copy(alpha = 0.3f)))
            Column(
                Modifier.weight(0.9f).quietClickable { cycle.power?.let(onOpenChart) }.padding(start = 12.dp),
            ) {
                Text("MOC", color = FrigoTextMuted, style = LabelStyle.copy(fontSize = 12.sp), maxLines = 1)
                Text(reading(cycle.power), color = FrigoMax, style = ValueStyle.copy(fontSize = 24.sp), maxLines = 1)
            }
        }
    }
}
