package pl.frigocore.service.ui.overview

import pl.frigocore.service.ui.theme.TabularNumbers
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.MessageState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.sensor.ChartPoint
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoMax
import pl.frigocore.service.ui.theme.FrigoMin
import pl.frigocore.service.ui.theme.FrigoOk
import pl.frigocore.service.ui.theme.FrigoOutline
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
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    val objectAlarms = uiState.openAlarms.filter { it.object_id == uiState.selectedObjectId }
                    items(objectAlarms, key = { "alarm-${it.id}" }) { alarm ->
                        AlarmBanner(alarm) { onAlarmClick(alarm.id) }
                    }
                    itemsIndexed(uiState.cards, key = { _, card -> card.sensor.id }) { i, card ->
                        if (i > 0) HorizontalDivider(color = FrigoAccent.copy(alpha = 0.45f))
                        SensorCardView(card) { onSensorClick(card.sensor) }
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
                    "${Formatters.alarmType(alarm.alarm_type)}${alarm.sensor_name.takeIf { it.isNotBlank() }?.let { " — $it" } ?: ""}",
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

@Composable
private fun SensorCardView(card: SensorCard, onClick: () -> Unit) {
    val tempColor = when (card.status) {
        SensorStatus.OK -> heatColor(tempHeat(card.sensor.current_temperature, card.stats))
        SensorStatus.ALARM -> FrigoCritical
        SensorStatus.OFFLINE -> FrigoTextMuted
    }
    // No card chrome: each sensor is a section, separated by a thin line in the list.
    Column(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(start = 4.dp, end = 4.dp, top = 16.dp, bottom = 14.dp),
    ) {
        CardTitle(card.sensor.name, card.status)
        Spacer(Modifier.height(6.dp))
        Row(Modifier.height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
            Text(
                buildAnnotatedString {
                    append(Formatters.temperatureValue(card.sensor.current_temperature))
                    withStyle(SpanStyle(fontSize = 28.sp)) { append("°C") }
                },
                color = tempColor,
                fontWeight = FontWeight.Bold,
                fontSize = 38.sp,
                maxLines = 1,
                style = TabularNumbers,
            )
            Spacer(Modifier.width(12.dp))
            // 24 h min / average / max — colour says which is which.
            StatDivider()
            Stat(card.stats?.min, FrigoMin, Modifier.weight(1f))
            StatDivider()
            Stat(card.stats?.avg, FrigoOk, Modifier.weight(1f))
            StatDivider()
            Stat(card.stats?.max, FrigoMax, Modifier.weight(1f))
        }
        Spacer(Modifier.height(16.dp))
        CardChart(card.history, Modifier.fillMaxWidth().height(120.dp))
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

/** Sensor name, top-right; a non-OK status is appended in its own colour. */
@Composable
private fun CardTitle(name: String, status: SensorStatus) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        Text(
            name.uppercase(),
            color = FrigoTextMuted,
            fontSize = 15.sp,
            fontWeight = FontWeight.Normal,
            letterSpacing = 0.5.sp,
            maxLines = 1,
        )
        if (status != SensorStatus.OK) {
            Text(
                " · ${status.name}",
                color = if (status == SensorStatus.ALARM) FrigoCritical else FrigoTextMuted,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun StatDivider() {
    VerticalDivider(Modifier.fillMaxHeight().padding(vertical = 4.dp), thickness = 1.dp, color = FrigoAccent.copy(alpha = 0.35f))
}

@Composable
private fun Stat(value: Double?, color: Color, modifier: Modifier = Modifier) {
    Text(
        Formatters.temperature(value),
        color = color,
        fontSize = 15.sp,
        style = TabularNumbers,
        fontWeight = FontWeight.Medium,
        maxLines = 1,
        textAlign = TextAlign.Center,
        modifier = modifier,
    )
}

/** Last 24 h with a degree axis (three whole-degree ticks) and a time axis
 * every 4 h, filled under the line. Tapping the card opens the full chart. */
@Composable
private fun CardChart(points: List<ChartPoint>, modifier: Modifier = Modifier) {
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

        // Time axis + dashed vertical grid every 4 h, ticked below the axis
        val dash = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 4.dp.toPx()))
        // A tick before the window start would pile up on the left edge.
        hourTicks(now).filter { it.toEpochMilli() >= tStart }.forEach { t ->
            val xx = x(t)
            drawLine(FrigoOutline, Offset(xx, topPad), Offset(xx, topPad + chartH), 1f, pathEffect = dash)
            drawLine(FrigoTextMuted, Offset(xx, topPad + chartH), Offset(xx, topPad + chartH + 4.dp.toPx()), 1f)
            val label = textMeasurer.measure(t.atZone(ZoneId.systemDefault()).format(hourFormat), labelStyle)
            val lx = (xx - label.size.width / 2).coerceIn(0f, size.width - label.size.width)
            drawText(label, topLeft = Offset(lx, size.height - label.size.height))
        }

        val visible = points.filter { it.time.toEpochMilli() >= tStart }
        if (visible.size < 2) return@Canvas
        val line = Path()
        // Step line: hold each reading level until the next one, then jump.
        visible.forEachIndexed { i, p ->
            if (i == 0) line.moveTo(x(p.time), y(p.value))
            else {
                line.lineTo(x(p.time), y(visible[i - 1].value))
                line.lineTo(x(p.time), y(p.value))
            }
        }
        val fill = Path().apply {
            addPath(line)
            lineTo(x(visible.last().time), topPad + chartH)
            lineTo(x(visible.first().time), topPad + chartH)
            close()
        }
        drawPath(
            fill,
            Brush.verticalGradient(listOf(FrigoAccent.copy(alpha = 0.55f), FrigoAccent.copy(alpha = 0.04f)), topPad, topPad + chartH),
        )
        drawPath(line, FrigoAccent, style = Stroke(width = 1.5.dp.toPx(), join = StrokeJoin.Miter))
    }
}
