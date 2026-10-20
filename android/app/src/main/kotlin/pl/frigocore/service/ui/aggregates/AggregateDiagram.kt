package pl.frigocore.service.ui.aggregates

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material3.IconButton
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.text.style.TextOverflow
import pl.frigocore.service.data.model.AggregateResponse
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
import androidx.compose.material.icons.outlined.LocalFireDepartment
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

/** The aggregate on one card: name and compressor model on top, the
 * refrigeration cycle as a picture — compressor with the discharge (red)
 * and suction (blue) lines, condenser bottom left, the liquid line (yellow)
 * across to the receivers, each with its reading — then the outdoor
 * temperature, current and power, and the nameplate facts as rows.
 * Tapping a reading opens its chart; [onBack] returns to the tiles when
 * there are several aggregates. */
@Composable
internal fun AggregatePage(
    aggregate: AggregateResponse,
    cycle: CycleSensors,
    onBack: (() -> Unit)?,
    onOpenChart: (SensorResponse) -> Unit,
) {
    Card(
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(1.dp, FrigoAccent.copy(alpha = 0.3f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(start = if (onBack != null) 4.dp else 16.dp, end = 16.dp, top = 12.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (onBack != null) {
                IconButton(onClick = onBack, modifier = Modifier.size(40.dp)) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Wszystkie agregaty", tint = FrigoAccent)
                }
            }
            Text(
                aggregate.name.uppercase(),
                color = FrigoText,
                style = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Bold, fontSize = 30.sp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false),
            )
            aggregate.compressor_model?.let {
                Spacer(Modifier.width(12.dp))
                Text(
                    it,
                    color = FrigoAccent,
                    style = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.SemiBold, fontSize = 24.sp),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Box(Modifier.padding(horizontal = 16.dp).fillMaxWidth().height(1.dp).background(FrigoAccent.copy(alpha = 0.25f)))

        BoxWithConstraints(Modifier.fillMaxWidth().aspectRatio(1f / 0.8f).padding(8.dp)) {
            val w = maxWidth
            val h = maxHeight
            Canvas(Modifier.fillMaxSize()) { drawCycle() }
            // Fan discs: flame on the condenser, snowflake on the receivers.
            Icon(
                Icons.Outlined.LocalFireDepartment, contentDescription = null, tint = FrigoMax,
                modifier = Modifier.centeredAt(w * 0.2f, h * UNIT_Y, 30.dp),
            )
            Icon(
                Icons.Outlined.AcUnit, contentDescription = null, tint = FrigoAccent,
                modifier = Modifier.centeredAt(w * 0.8f, h * UNIT_Y, 30.dp),
            )
            Reading("TŁOCZENIE", reading(cycle.discharge), FrigoCritical, w * 0.27f, h * 0.02f) { onOpenChart(cycle.discharge) }
            Reading("SSANIE", reading(cycle.suction), FrigoAccent, w * 0.73f, h * 0.02f) { onOpenChart(cycle.suction) }
            Reading("SPRĘŻARKA", reading(cycle.compressor), FrigoCritical, w * 0.5f, h * 0.4f) {
                cycle.compressor?.let(onOpenChart)
            }
            // The condenser's reading sits on the compressor's axis, under the liquid line.
            Reading("SKRAPLACZ", reading(cycle.condenser), Liquid, w * 0.5f, h * (UNIT_Y + 0.05f)) { onOpenChart(cycle.condenser) }
            Reading("ODBIORNIKI", null, FrigoText, w * 0.8f, h * (UNIT_Y + 0.15f)) {}
        }
        ElectricRow(cycle, onOpenChart)
        Column(
            Modifier.fillMaxWidth().padding(start = 10.dp, end = 10.dp, top = 10.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FactRow({ Icon(Icons.Outlined.AcUnit, null, tint = FrigoAccent, modifier = Modifier.size(30.dp)) },
                "MOC CHŁODNICZA", aggregate.cooling_capacity_kw?.let { formatAmount(it, "kW") })
            FactRow({ CylinderIcon(FrigoAccent) }, "CZYNNIK", aggregate.refrigerant)
            FactRow({ WeightIcon(FrigoAccent) }, "WAGA CZYNNIKA", aggregate.refrigerant_charge_kg?.let { formatAmount(it, "kg") })
            FactRow({ Icon(Icons.Outlined.CalendarMonth, null, tint = FrigoAccent, modifier = Modifier.size(30.dp)) },
                "DATA INSTALACJI", aggregate.installed_on?.let(::longDate))
        }
    }
}

private val longDateFormat = java.time.format.DateTimeFormatter.ofPattern("dd.MM.yyyy")

/** "2026-10-19" → "19.10.2026"; anything unparsable is shown as sent. */
private fun longDate(iso: String): String =
    runCatching { java.time.LocalDate.parse(iso).format(longDateFormat) }.getOrDefault(iso)

/** A framed row: icon, label, and the value at the far right. */
@Composable
private fun FactRow(icon: @Composable () -> Unit, label: String, value: String?) {
    Row(
        Modifier
            .fillMaxWidth()
            .height(48.dp)
            .background(FrigoBackground.copy(alpha = 0.45f), RoundedCornerShape(10.dp))
            .border(1.dp, FrigoOutline, RoundedCornerShape(10.dp))
            .padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(34.dp), contentAlignment = Alignment.Center) { icon() }
        Spacer(Modifier.width(16.dp))
        Text(
            label,
            color = FrigoText.copy(alpha = 0.85f),
            style = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 18.sp, letterSpacing = 0.5.sp),
            maxLines = 1,
            modifier = Modifier.weight(1f),
        )
        Text(
            value ?: "—",
            color = FrigoText,
            style = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.SemiBold, fontSize = 22.sp, fontFeatureSettings = "tnum"),
            maxLines = 1,
        )
    }
}

/** Refrigerant bottle: a rounded body with a collar and a valve on top. */
@Composable
private fun CylinderIcon(color: Color) {
    Canvas(Modifier.size(30.dp)) {
        val s = size.width
        val stroke = Stroke(2.dp.toPx())
        drawRoundRect(color, Offset(s * 0.22f, s * 0.3f), Size(s * 0.56f, s * 0.66f), CornerRadius(s * 0.12f), style = stroke)
        drawRoundRect(color, Offset(s * 0.32f, s * 0.14f), Size(s * 0.36f, s * 0.16f), CornerRadius(s * 0.04f), style = stroke)
        drawLine(color, Offset(s * 0.5f, s * 0.02f), Offset(s * 0.5f, s * 0.14f), 2.dp.toPx())
        drawLine(color, Offset(s * 0.38f, s * 0.04f), Offset(s * 0.62f, s * 0.04f), 2.dp.toPx())
        drawLine(color, Offset(s * 0.22f, s * 0.55f), Offset(s * 0.78f, s * 0.55f), 1.5.dp.toPx())
        drawCircle(color, s * 0.05f, Offset(s * 0.5f, s * 0.72f))
    }
}

/** Weight: a bell-shaped block with a ring on top and "kg" on it. */
@Composable
private fun WeightIcon(color: Color) {
    Box(Modifier.size(32.dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val s = size.width
            val stroke = Stroke(2.dp.toPx(), join = StrokeJoin.Round)
            drawCircle(color, s * 0.1f, Offset(s * 0.5f, s * 0.14f), style = stroke)
            val body = Path().apply {
                moveTo(s * 0.3f, s * 0.26f)
                lineTo(s * 0.7f, s * 0.26f)
                lineTo(s * 0.9f, s * 0.94f)
                lineTo(s * 0.1f, s * 0.94f)
                close()
            }
            drawPath(body, color, style = stroke)
        }
        Text(
            "kg",
            color = color,
            style = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Bold, fontSize = 11.sp),
            modifier = Modifier.padding(top = 9.dp),
        )
    }
}

/** A house with a thermometer standing by it — the outdoor temperature. */
@Composable
private fun HouseThermometerIcon(color: Color, mercury: Color) {
    Canvas(Modifier.size(38.dp)) {
        val s = size.width
        val stroke = Stroke(2.dp.toPx(), join = StrokeJoin.Round, cap = StrokeCap.Round)
        val house = Path().apply {
            moveTo(s * 0.62f, s * 0.92f)
            lineTo(s * 0.08f, s * 0.92f)
            lineTo(s * 0.08f, s * 0.48f)
            lineTo(s * 0.38f, s * 0.18f)
            lineTo(s * 0.62f, s * 0.42f)
        }
        drawPath(house, color, style = stroke)
        drawLine(color, Offset(s * 0.02f, s * 0.54f), Offset(s * 0.38f, s * 0.18f), 2.dp.toPx(), cap = StrokeCap.Round)
        // Door.
        drawRect(color, Offset(s * 0.24f, s * 0.66f), Size(s * 0.16f, s * 0.26f), style = Stroke(1.6.dp.toPx()))
        // Thermometer: tube and bulb.
        drawRoundRect(color, Offset(s * 0.7f, s * 0.12f), Size(s * 0.16f, s * 0.6f), CornerRadius(s * 0.08f), style = stroke)
        drawCircle(mercury, s * 0.12f, Offset(s * 0.78f, s * 0.82f))
        drawCircle(color, s * 0.12f, Offset(s * 0.78f, s * 0.82f), style = stroke)
        drawLine(mercury, Offset(s * 0.78f, s * 0.36f), Offset(s * 0.78f, s * 0.74f), 3.dp.toPx(), cap = StrokeCap.Round)
    }
}

/** A heartbeat trace — the power being drawn. */
@Composable
private fun PulseIcon(color: Color) {
    Canvas(Modifier.size(32.dp)) {
        val s = size.width
        val trace = Path().apply {
            moveTo(0f, s * 0.55f)
            lineTo(s * 0.28f, s * 0.55f)
            lineTo(s * 0.4f, s * 0.15f)
            lineTo(s * 0.55f, s * 0.9f)
            lineTo(s * 0.66f, s * 0.42f)
            lineTo(s * 0.74f, s * 0.55f)
            lineTo(s, s * 0.55f)
        }
        drawPath(trace, color, style = Stroke(2.2.dp.toPx(), join = StrokeJoin.Round, cap = StrokeCap.Round))
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
    compressor(Offset(w * 0.5f, topY), w * 0.2f)
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

/** Light steel of the flat unit icons on the dark card. */
private val Steel = Color(0xFFB4C1D4)
/** Shadowed steel for seams and the darker parts. */
private val SteelDark = Color(0xFF5F6F86)

/** A finned coil in the flat icon style: a serpentine tube running back
 * and forth over a comb of fins, with a fan disc in the middle (its
 * icon — flame on the condenser, snowflake on the receivers — goes on top
 * in [color]). */
private fun DrawScope.coil(center: Offset, s: Size, color: Color) {
    val left = center.x - s.width / 2
    val right = center.x + s.width / 2
    val top = center.y - s.height / 2
    val rows = 4
    val gap = s.height / (rows - 1)
    val r = gap / 2
    val tube = 3.2.dp.toPx()

    // Fins: a comb of thin uprights behind the tube.
    val finTop = top - gap * 0.18f
    val finBottom = top + s.height + gap * 0.18f
    var x = left + r + 4.dp.toPx()
    while (x < right - r - 2.dp.toPx()) {
        drawLine(Steel.copy(alpha = 0.55f), Offset(x, finTop), Offset(x, finBottom), 1.6.dp.toPx())
        x += 7.dp.toPx()
    }

    // The tube: in at the top left, back and forth with U-bends, out at the bottom right.
    val path = Path().apply {
        moveTo(left - r * 0.6f, top - r * 0.9f)
        quadraticBezierTo(left - r * 0.6f, top, left + r * 0.4f, top)
        for (i in 0 until rows) {
            val y = top + i * gap
            val goingRight = i % 2 == 0
            val endX = if (goingRight) right - r else left + r
            lineTo(endX, y)
            if (i < rows - 1) {
                // A U-bend down to the next row on this side.
                val cx = endX
                val rect = androidx.compose.ui.geometry.Rect(cx - r, y, cx + r, y + gap)
                arcTo(rect, -90f, if (goingRight) 180f else -180f, false)
            }
        }
        val lastY = top + (rows - 1) * gap
        val outX = if ((rows - 1) % 2 == 0) right + r * 0.6f else left - r * 0.6f
        quadraticBezierTo(outX, lastY, outX, lastY + r * 0.9f)
    }
    drawPath(path, Steel, style = Stroke(tube, cap = StrokeCap.Round, join = StrokeJoin.Round))

    // Fan disc.
    val disc = s.height * 0.4f
    drawCircle(FrigoBackground, disc, center)
    drawCircle(Steel, disc, center, style = Stroke(3.dp.toPx()))
    drawCircle(color.copy(alpha = 0.12f), disc - 3.dp.toPx(), center)
}

/** A rotary compressor in the flat icon style: a tall rounded shell with
 * the terminal on top, the suction accumulator standing at its side joined
 * by two short pipes, all on a base plate. */
private fun DrawScope.compressor(center: Offset, width: Float) {
    val bodyW = width * 0.56f
    val bodyH = width * 0.95f
    val bodyLeft = center.x - width * 0.36f
    val bodyTop = center.y - bodyH * 0.5f
    val base = bodyTop + bodyH

    // Base plate.
    drawRoundRect(Steel, Offset(center.x - width * 0.5f, base + 2.dp.toPx()), Size(width, 4.dp.toPx()), CornerRadius(1.dp.toPx()))
    // Feet.
    drawRect(SteelDark, Offset(bodyLeft + bodyW * 0.15f, base - 1.dp.toPx()), Size(bodyW * 0.7f, 3.dp.toPx()))

    // Terminal: a cap and a stem on the dome.
    val stemX = bodyLeft + bodyW / 2
    drawRect(Steel, Offset(stemX - 2.dp.toPx(), bodyTop - 7.dp.toPx()), Size(4.dp.toPx(), 8.dp.toPx()))
    drawRoundRect(Steel, Offset(stemX - 6.dp.toPx(), bodyTop - 10.dp.toPx()), Size(12.dp.toPx(), 4.dp.toPx()), CornerRadius(1.dp.toPx()))

    // Shell.
    drawRoundRect(Steel, Offset(bodyLeft, bodyTop), Size(bodyW, bodyH), CornerRadius(bodyW * 0.22f))
    // Seams.
    drawLine(SteelDark, Offset(bodyLeft, bodyTop + bodyH * 0.18f), Offset(bodyLeft + bodyW, bodyTop + bodyH * 0.18f), 1.5.dp.toPx())
    drawLine(SteelDark, Offset(bodyLeft, bodyTop + bodyH * 0.82f), Offset(bodyLeft + bodyW, bodyTop + bodyH * 0.82f), 1.5.dp.toPx())
    drawLine(Color.White.copy(alpha = 0.35f), Offset(bodyLeft + bodyW * 0.2f, bodyTop + bodyH * 0.26f), Offset(bodyLeft + bodyW * 0.2f, bodyTop + bodyH * 0.74f), 2.5.dp.toPx(), cap = StrokeCap.Round)

    // Accumulator: a slim capsule at the side with its own stem.
    val accW = width * 0.2f
    val accH = bodyH * 0.6f
    val accLeft = bodyLeft + bodyW + width * 0.12f
    val accTop = center.y - accH * 0.62f
    drawRect(Steel, Offset(accLeft + accW / 2 - 1.5.dp.toPx(), accTop - 6.dp.toPx()), Size(3.dp.toPx(), 7.dp.toPx()))
    drawRoundRect(Steel, Offset(accLeft + accW / 2 - 4.dp.toPx(), accTop - 8.dp.toPx()), Size(8.dp.toPx(), 3.dp.toPx()), CornerRadius(1.dp.toPx()))
    drawRoundRect(Steel, Offset(accLeft, accTop), Size(accW, accH), CornerRadius(accW * 0.45f))
    drawLine(SteelDark, Offset(accLeft, accTop + accH * 0.5f), Offset(accLeft + accW, accTop + accH * 0.5f), 1.5.dp.toPx())
    // Pipes from the accumulator into the shell: one at the band, one low down into the base.
    val pipe = 3.dp.toPx()
    drawLine(Steel, Offset(bodyLeft + bodyW - 1.dp.toPx(), accTop + accH * 0.5f), Offset(accLeft + 1.dp.toPx(), accTop + accH * 0.5f), pipe)
    val outX = accLeft + accW / 2
    drawLine(Steel, Offset(outX, accTop + accH), Offset(outX, bodyTop + bodyH * 0.9f), pipe, cap = StrokeCap.Round)
    drawLine(Steel, Offset(outX, bodyTop + bodyH * 0.9f), Offset(bodyLeft + bodyW - 1.dp.toPx(), bodyTop + bodyH * 0.9f), pipe, cap = StrokeCap.Round)

    // Discharge stub on the left, where the red line leaves.
    drawRect(FrigoCritical, Offset(bodyLeft - 6.dp.toPx(), center.y - 4.dp.toPx()), Size(7.dp.toPx(), 8.dp.toPx()))
}

/** Outdoor temperature, current and power side by side. */
@Composable
private fun ElectricRow(cycle: CycleSensors, onOpenChart: (SensorResponse) -> Unit) {
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, FrigoOutline),
        colors = CardDefaults.cardColors(containerColor = FrigoBackground.copy(alpha = 0.4f), contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 10.dp),
    ) {
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min).padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Row(
                Modifier.weight(1f).quietClickable { cycle.outdoor?.let(onOpenChart) }.padding(start = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                HouseThermometerIcon(Color(0xFFC9D3E3), FrigoAccent)
                Spacer(Modifier.width(8.dp))
                Column {
                    Text("TEMP.", color = FrigoTextMuted, style = LabelStyle.copy(fontSize = 12.sp), maxLines = 1)
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
            Row(
                Modifier.weight(1.1f).quietClickable { cycle.power?.let(onOpenChart) }.padding(start = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                PulseIcon(FrigoText)
                Spacer(Modifier.width(6.dp))
                Column {
                    Text("MOC", color = FrigoTextMuted, style = LabelStyle.copy(fontSize = 12.sp), maxLines = 1)
                    Text(reading(cycle.power), color = FrigoMax, style = ValueStyle.copy(fontSize = 24.sp), maxLines = 1)
                }
            }
        }
    }
}
