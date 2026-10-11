package pl.frigocore.service.ui.overview

import pl.frigocore.service.ui.theme.TabularNumbers
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.MessageState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.common.quietClickable
import pl.frigocore.service.ui.sensor.ChartPoint
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoMax
import pl.frigocore.service.ui.theme.FrigoMin
import pl.frigocore.service.ui.theme.FrigoOk
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

@Composable
fun OverviewScreen(
    onSensorClick: (SensorResponse) -> Unit,
    onAlarmClick: (String) -> Unit,
    viewModel: OverviewViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible { viewModel.refresh() }
    // Sensors start as a list of slim rows so as many as possible fit on
    // one phone screen; a tapped row unfolds into the chart and 24 h stats.
    var expanded by rememberSaveable { mutableStateOf(emptyList<String>()) }

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        Spacer(Modifier.height(10.dp))
        Box(Modifier.weight(1f)) {
            when {
                uiState.isLoading && uiState.cards.isEmpty() -> LoadingState()
                uiState.error != null && uiState.cards.isEmpty() -> MessageState(uiState.error.orEmpty(), viewModel::refresh)
                uiState.objects.isEmpty() ->
                    MessageState("Nie masz jeszcze przypisanych obiektów.\nSkontaktuj się z administratorem.")
                uiState.cards.isEmpty() -> MessageState("Ten obiekt nie ma jeszcze czujników.")
                else -> LazyColumn(
                    contentPadding = PaddingValues(bottom = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    val objectAlarms = uiState.openAlarms.filter { it.object_id == uiState.selectedObjectId }
                    items(objectAlarms, key = { "alarm-${it.id}" }) { alarm ->
                        AlarmBanner(alarm) { onAlarmClick(alarm.id) }
                    }
                    items(uiState.cards, key = { it.sensor.id }) { card ->
                        val id = card.sensor.id
                        SensorCardView(
                            card,
                            expanded = id in expanded,
                            onToggle = { expanded = if (id in expanded) expanded - id else expanded + id },
                            onOpenChart = { onSensorClick(card.sensor) },
                        )
                    }
                }
            }
        }
    }
}

private val hourFormat = DateTimeFormatter.ofPattern("HH:mm")

@Composable
private fun AlarmBanner(alarm: AlarmResponse, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        colors = CardDefaults.cardColors(containerColor = FrigoCritical.copy(alpha = 0.18f), contentColor = FrigoText),
        border = BorderStroke(1.dp, FrigoCritical),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Warning, contentDescription = null, tint = FrigoCritical)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "${Formatters.alarmType(alarm.alarm_type, alarm.sensor_kind)}${alarm.sensor_name.takeIf { it.isNotBlank() }?.let { " — $it" } ?: ""}",
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    "${Formatters.alarmStatus(alarm.status)} · ${Formatters.dateTime(alarm.detected_at)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = FrigoTextMuted,
                )
            }
            Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = FrigoTextMuted)
        }
    }
}

/** A slim row — name and current reading — that a tap unfolds into the
 * 24 h chart and MIN / ŚREDNIA / MAX. Also used on the aggregate screen. */
@Composable
internal fun SensorCardView(card: SensorCard, expanded: Boolean, onToggle: () -> Unit, onOpenChart: () -> Unit) {
    // The name, the current reading and the chart share one colour: the 24 h
    // trend, or the alarm / offline state when that applies.
    val trendColor = when (card.status) {
        SensorStatus.OK -> heatColor(tempHeat(card.sensor.current_temperature, card.stats))
        SensorStatus.ALARM -> FrigoCritical
        SensorStatus.OFFLINE -> FrigoTextMuted
    }
    val edge = if (card.status == SensorStatus.ALARM) FrigoCritical else FrigoAccent
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, edge.copy(alpha = if (card.status == SensorStatus.ALARM) 0.8f else 0.35f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth().quietClickable(onToggle),
    ) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) {
            Row(Modifier.heightIn(min = 34.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    CardTitle(card.sensor.name, card.status, trendColor)
                    if (card.status == SensorStatus.OFFLINE) {
                        Text(
                            "Ostatni odczyt: ${Formatters.ago(card.sensor.last_message_at)}",
                            color = FrigoTextMuted,
                            fontSize = 12.sp,
                            maxLines = 1,
                        )
                    }
                }
                Spacer(Modifier.width(8.dp))
                Text(
                    buildAnnotatedString {
                        append(Formatters.readingValue(card.sensor.current_temperature, card.sensor.unit))
                        val unit = card.sensor.unit
                        withStyle(SpanStyle(fontSize = 15.sp)) { append(if (unit == "°C") unit else " $unit") }
                    },
                    color = trendColor,
                    fontWeight = FontWeight.Bold,
                    fontSize = 22.sp,
                    maxLines = 1,
                    style = TabularNumbers,
                )
            }
            AnimatedVisibility(expanded) {
                Column {
                    Spacer(Modifier.height(8.dp))
                    // A second tap, on the chart, opens it full screen.
                    CardChart(card.history, trendColor, Modifier.fillMaxWidth().height(130.dp).quietClickable(onOpenChart))
                    Spacer(Modifier.height(10.dp))
                    // 24 h min / average / max, all in the brand colour.
                    Row(Modifier.height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
                        Stat("MIN", card.stats?.min, card.sensor.unit, Modifier.weight(1f))
                        StatDivider()
                        Stat("ŚREDNIA", card.stats?.avg, card.sensor.unit, Modifier.weight(1f))
                        StatDivider()
                        Stat("MAX", card.stats?.max, card.sensor.unit, Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

/** Green around the 24 h average, sliding through orange to red towards
 * the max and to blue towards the min. */
private fun heatColor(heat: Double?): Color = when {
    heat == null -> FrigoText
    heat >= 0.3 -> if (heat < 0.65) lerp(FrigoOk, FrigoMax, ((heat - 0.3) / 0.35).toFloat())
        else lerp(FrigoMax, FrigoCritical, ((heat - 0.65) / 0.35).toFloat())
    heat <= -0.3 -> lerp(FrigoOk, FrigoMin, ((-heat - 0.3) / 0.7).toFloat())
    else -> FrigoOk
}

/** Sensor name, top-left, in [color]; a non-OK status is appended to it. */
@Composable
private fun CardTitle(name: String, status: SensorStatus, color: Color, modifier: Modifier = Modifier) {
    Text(
        buildAnnotatedString {
            append(name.uppercase())
            if (status != SensorStatus.OK) append(" · ${status.name}")
        },
        color = color,
        fontSize = 16.sp,
        fontWeight = FontWeight.Bold,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
        modifier = modifier,
    )
}

@Composable
internal fun StatDivider() {
    VerticalDivider(Modifier.fillMaxHeight().padding(vertical = 4.dp), thickness = 1.dp, color = FrigoAccent.copy(alpha = 0.35f))
}

@Composable
internal fun Stat(label: String, value: Double?, unit: String, modifier: Modifier = Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, color = FrigoTextMuted, fontSize = 12.sp, letterSpacing = 0.5.sp, maxLines = 1)
        Text(
            Formatters.reading(value, unit),
            color = FrigoAccent,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            style = TabularNumbers,
        )
    }
}

/** Last 24 h as a step line in [color] over a three-level grid, with five
 * time labels from the window start to now, filled under the line. Tapping the card opens the full chart. */
@Composable
internal fun CardChart(
    points: List<ChartPoint>,
    color: Color,
    modifier: Modifier = Modifier,
) {
    val textMeasurer = rememberTextMeasurer()
    val labelStyle = TextStyle(fontSize = 12.sp, color = FrigoText.copy(alpha = 0.75f))
    Canvas(modifier) {
        if (points.size < 2) return@Canvas
        val now = Instant.now()
        val tStart = now.minus(24, ChronoUnit.HOURS).toEpochMilli()
        val tSpan = (now.toEpochMilli() - tStart).toFloat()
        val (lo, step) = cardAxis(points.minOf { it.value }, points.maxOf { it.value })
        val hi = lo + 2 * step

        val leftPad = 0f
        val bottomPad = 24.dp.toPx()
        val topPad = 6.dp.toPx()
        val chartW = size.width - leftPad
        val chartH = size.height - bottomPad - topPad
        fun x(t: Instant) = leftPad + ((t.toEpochMilli() - tStart) / tSpan).coerceIn(0f, 1f) * chartW
        fun y(v: Double) = topPad + ((hi - v) / (hi - lo)).toFloat() * chartH

        // Horizontal grid on the three whole-degree levels; no degree labels,
        // so the plot runs the full width of the section.
        for (i in 0..2) {
            val yy = y((lo + i * step).toDouble())
            drawLine(if (i == 0) FrigoTextMuted else FrigoOutline, Offset(leftPad, yy), Offset(size.width, yy), 1f)
        }

        // Time axis: five evenly spaced labels across the window (start, every
        // 6 h, now), each with a dashed grid line and a tick below the axis.
        val dash = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 4.dp.toPx()))
        for (i in 0..4) {
            val f = i / 4f
            val t = Instant.ofEpochMilli(tStart + (tSpan * f).toLong())
            val xx = leftPad + chartW * f
            drawLine(FrigoOutline, Offset(xx, topPad), Offset(xx, topPad + chartH), 1f, pathEffect = dash)
            drawLine(FrigoTextMuted, Offset(xx, topPad + chartH), Offset(xx, topPad + chartH + 4.dp.toPx()), 1f)
            val label = textMeasurer.measure(t.atZone(ZoneId.systemDefault()).format(hourFormat), labelStyle)
            // First label hangs right of its tick, last one left of it, the rest centred.
            val lx = (xx - label.size.width * f).coerceIn(0f, size.width - label.size.width)
            drawText(label, topLeft = Offset(lx, size.height - label.size.height))
        }

        // Step line: hold each reading level until the next one, then jump.
        fun stepLine(series: List<ChartPoint>) = Path().apply {
            series.forEachIndexed { i, p ->
                if (i == 0) moveTo(x(p.time), y(p.value))
                else {
                    lineTo(x(p.time), y(series[i - 1].value))
                    lineTo(x(p.time), y(p.value))
                }
            }
        }

        val visible = points.filter { it.time.toEpochMilli() >= tStart }
        if (visible.size < 2) return@Canvas
        val line = stepLine(visible)
        val fill = Path().apply {
            addPath(line)
            lineTo(x(visible.last().time), topPad + chartH)
            lineTo(x(visible.first().time), topPad + chartH)
            close()
        }
        drawPath(
            fill,
            Brush.verticalGradient(listOf(color.copy(alpha = 0.55f), color.copy(alpha = 0.04f)), topPad, topPad + chartH),
        )
        drawPath(line, color, style = Stroke(width = 1.5.dp.toPx(), join = StrokeJoin.Miter))
    }
}
