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
 * refrigeration cycle as a control-panel schematic ([CycleSchematic]) with
 * the discharge, suction, compressor and condenser readings — then the outdoor
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

        CycleSchematic(cycle, onOpenChart)
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
