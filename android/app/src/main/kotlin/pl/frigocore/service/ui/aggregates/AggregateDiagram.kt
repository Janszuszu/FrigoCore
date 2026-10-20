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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
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
        BoxWithConstraints(Modifier.fillMaxWidth().aspectRatio(1f / 0.92f).padding(8.dp)) {
            val w = maxWidth
            val h = maxHeight
            Canvas(Modifier.fillMaxSize()) { drawCycle() }
            // Fan discs: sun on the condenser, snowflake on the receivers.
            Icon(
                Icons.Outlined.WbSunny, contentDescription = null, tint = Liquid,
                modifier = Modifier.centeredAt(w * 0.2f, h * UNIT_Y, 30.dp),
            )
            Icon(
                Icons.Outlined.AcUnit, contentDescription = null, tint = FrigoAccent,
                modifier = Modifier.centeredAt(w * 0.8f, h * UNIT_Y, 30.dp),
            )
            Reading("TŁOCZENIE", reading(cycle.discharge), FrigoCritical, w * 0.27f, h * 0.02f) { onOpenChart(cycle.discharge) }
            Reading("SSANIE", reading(cycle.suction), FrigoAccent, w * 0.73f, h * 0.02f) { onOpenChart(cycle.suction) }
            Reading("SPRĘŻARKA", reading(cycle.compressor), FrigoCritical, w * 0.5f, h * 0.36f) {
                cycle.compressor?.let(onOpenChart)
            }
            // The condenser's reading sits on the compressor's axis, under the liquid line.
            Reading("SKRAPLACZ", reading(cycle.condenser), Liquid, w * 0.5f, h * (UNIT_Y + 0.05f)) { onOpenChart(cycle.condenser) }
            Reading("ODBIORNIKI", null, FrigoText, w * 0.8f, h * (UNIT_Y + 0.15f)) {}
        }
        Spacer(Modifier.height(10.dp))
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

/** Height of the coils' centre line (and the liquid line), as a share of the box. */
private const val UNIT_Y = 0.66f

/** Neon magenta of the compressor. */
private val Neon = Color(0xFFFF2E97)

private fun DrawScope.drawCycle() {
    val w = size.width
    val h = size.height
    val pipe = 6.dp.toPx()
    val radius = 22.dp.toPx()
    val topY = h * 0.25f
    val unitY = h * UNIT_Y
    val unitTop = unitY - h * 0.12f
    val leftX = w * 0.12f
    val rightX = w * 0.88f
    val compLeft = w * 0.42f
    val compRight = w * 0.58f

    fun line(color: Color, pts: List<Offset>) {
        val path = Path().apply {
            moveTo(pts[0].x, pts[0].y)
            for (i in 1 until pts.size) lineTo(pts[i].x, pts[i].y)
        }
        val corners = PathEffect.cornerPathEffect(radius)
        // A soft glow under the pipe.
        drawPath(path, color.copy(alpha = 0.18f), style = Stroke(width = pipe * 2.6f, cap = StrokeCap.Round, join = StrokeJoin.Round, pathEffect = corners))
        drawPath(path, color, style = Stroke(width = pipe, cap = StrokeCap.Round, join = StrokeJoin.Round, pathEffect = corners))
    }
    // Discharge: compressor → down into the condenser. Suction: receivers → compressor.
    line(FrigoCritical, listOf(Offset(compLeft, topY), Offset(leftX, topY), Offset(leftX, unitTop)))
    line(FrigoAccent, listOf(Offset(rightX, unitTop), Offset(rightX, topY), Offset(compRight, topY)))
    // Liquid line across the bottom.
    line(Liquid, listOf(Offset(w * 0.33f, unitY), Offset(w * 0.67f, unitY)))

    val a = 9.dp.toPx()
    arrow(Offset(w * 0.3f, topY - 14.dp.toPx()), Offset(-1f, 0f), FrigoCritical, a)
    arrow(Offset(leftX - 14.dp.toPx(), h * 0.42f), Offset(0f, 1f), FrigoCritical, a)
    arrow(Offset(w * 0.7f, topY - 14.dp.toPx()), Offset(-1f, 0f), FrigoAccent, a)
    arrow(Offset(w * 0.5f, unitY - 14.dp.toPx()), Offset(1f, 0f), Liquid, a)
    // Air through the coils: in from the left, chilled out to the right.
    for (dy in listOf(-1, 0, 1)) {
        arrow(Offset(w * 0.035f, unitY + dy * 16.dp.toPx()), Offset(1f, 0f), FrigoCritical, a * 0.8f)
        arrow(Offset(w * 0.965f, unitY + dy * 16.dp.toPx()), Offset(1f, 0f), FrigoAccent, a * 0.8f)
    }

    coil(Offset(w * 0.2f, unitY), Size(w * 0.26f, h * 0.24f), Liquid)
    coil(Offset(w * 0.8f, unitY), Size(w * 0.26f, h * 0.24f), FrigoAccent)
    compressor(Offset(w * 0.5f, topY), w * 0.17f)
}

/** A neon tube: a wide faint glow, a narrower brighter one, the line and a white-hot core. */
private fun DrawScope.neon(path: Path, color: Color, width: Float) {
    drawPath(path, color.copy(alpha = 0.10f), style = Stroke(width * 5f, join = StrokeJoin.Miter))
    drawPath(path, color.copy(alpha = 0.25f), style = Stroke(width * 2.6f, join = StrokeJoin.Miter))
    drawPath(path, color, style = Stroke(width, join = StrokeJoin.Miter))
    drawPath(path, Color.White.copy(alpha = 0.55f), style = Stroke(width * 0.35f, join = StrokeJoin.Miter))
}

/** A box with the top-left and bottom-right corners cut off — the cyberpunk panel. */
private fun chamfered(left: Float, top: Float, width: Float, height: Float, cut: Float) = Path().apply {
    moveTo(left + cut, top)
    lineTo(left + width, top)
    lineTo(left + width, top + height - cut)
    lineTo(left + width - cut, top + height)
    lineTo(left, top + height)
    lineTo(left, top + cut)
    close()
}

private fun hexagon(center: Offset, r: Float) = Path().apply {
    for (i in 0 until 6) {
        val angle = Math.toRadians(60.0 * i - 30.0)
        val x = center.x + r * Math.cos(angle).toFloat()
        val y = center.y + r * Math.sin(angle).toFloat()
        if (i == 0) moveTo(x, y) else lineTo(x, y)
    }
    close()
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

/** A coil as a neon panel: chamfered frame, fins as scan lines, corner
 * brackets, status ticks and a hexagonal fan ring (its icon goes on top). */
private fun DrawScope.coil(center: Offset, s: Size, color: Color) {
    val left = center.x - s.width / 2
    val top = center.y - s.height / 2
    val frame = chamfered(left, top, s.width, s.height, s.width * 0.14f)
    drawPath(frame, FrigoBackground.copy(alpha = 0.92f))
    val fins = 8
    for (i in 1 until fins) {
        val y = top + s.height * i / fins
        drawLine(color.copy(alpha = 0.22f), Offset(left + 5.dp.toPx(), y), Offset(left + s.width - 5.dp.toPx(), y), 1.dp.toPx())
    }
    neon(frame, color, 1.6.dp.toPx())
    // Brackets off the two square corners.
    val b = 7.dp.toPx()
    val bw = 2.dp.toPx()
    val tr = Offset(left + s.width + 4.dp.toPx(), top - 4.dp.toPx())
    drawLine(color, tr, tr + Offset(-b, 0f), bw)
    drawLine(color, tr, tr + Offset(0f, b), bw)
    val bl = Offset(left - 4.dp.toPx(), top + s.height + 4.dp.toPx())
    drawLine(color, bl, bl + Offset(b, 0f), bw)
    drawLine(color, bl, bl + Offset(0f, -b), bw)
    // Status ticks along the bottom edge.
    for (i in 0..2) {
        val x = left + s.width * 0.08f + i * 6.dp.toPx()
        drawLine(color.copy(alpha = 0.8f), Offset(x, top + s.height - 6.dp.toPx()), Offset(x + 3.dp.toPx(), top + s.height - 6.dp.toPx()), 2.dp.toPx())
    }
    // Fan: a dark disc inside a neon hexagon.
    val r = s.height * 0.38f
    drawCircle(FrigoBackground, r * 0.95f, center)
    drawCircle(color.copy(alpha = 0.10f), r * 0.95f, center)
    neon(hexagon(center, r), color, 1.4.dp.toPx())
}

/** Hermetic compressor as a neon unit: a chamfered magenta shell under a
 * cut dome, scan lines, a glowing cyan core and a terminal box. */
private fun DrawScope.compressor(center: Offset, width: Float) {
    val bodyH = width * 0.9f
    val top = center.y - bodyH * 0.55f
    val left = center.x - width / 2
    val domeH = width * 0.26f

    val base = Path().apply {
        moveTo(left - 6.dp.toPx(), top + bodyH + 5.dp.toPx())
        lineTo(left + width + 6.dp.toPx(), top + bodyH + 5.dp.toPx())
    }
    neon(base, Neon, 1.6.dp.toPx())

    val dome = Path().apply {
        moveTo(left + width * 0.12f, top + domeH)
        lineTo(left + width * 0.26f, top)
        lineTo(left + width * 0.74f, top)
        lineTo(left + width * 0.88f, top + domeH)
        close()
    }
    drawPath(dome, FrigoBackground)
    neon(dome, Neon, 1.4.dp.toPx())

    val shell = chamfered(left, top + domeH, width, bodyH - domeH, width * 0.16f)
    drawPath(shell, FrigoBackground)
    for (i in 1..5) {
        val y = top + domeH + (bodyH - domeH) * i / 6
        drawLine(Neon.copy(alpha = 0.18f), Offset(left + 4.dp.toPx(), y), Offset(left + width - 4.dp.toPx(), y), 1.dp.toPx())
    }
    neon(shell, Neon, 1.8.dp.toPx())

    // Glowing core.
    val core = Offset(center.x - width * 0.06f, top + domeH + (bodyH - domeH) * 0.5f)
    val cr = width * 0.14f
    drawCircle(FrigoAccent.copy(alpha = 0.15f), cr * 2.2f, core)
    drawCircle(FrigoAccent.copy(alpha = 0.35f), cr * 1.4f, core)
    drawCircle(FrigoAccent, cr, core, style = Stroke(1.6.dp.toPx()))
    drawCircle(Color.White.copy(alpha = 0.8f), cr * 0.35f, core)

    // Terminal box on the suction side.
    val bw = width * 0.3f
    val bh = bodyH * 0.38f
    val box = chamfered(left + width * 0.86f, center.y - bh / 2, bw, bh, bw * 0.3f)
    drawPath(box, FrigoBackground)
    neon(box, FrigoAccent, 1.2.dp.toPx())
    // Discharge stub on the left.
    drawRect(FrigoCritical, Offset(left - 7.dp.toPx(), center.y - 5.dp.toPx()), Size(7.dp.toPx(), 10.dp.toPx()))
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
