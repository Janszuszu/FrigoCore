package pl.frigocore.service.ui.overview

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
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
import pl.frigocore.service.ui.common.sensorIcon
import pl.frigocore.service.ui.sensor.ChartPoint
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoCritical
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
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    val objectAlarms = uiState.openAlarms.filter { it.object_id == uiState.selectedObjectId }
                    items(objectAlarms, key = { "alarm-${it.id}" }) { alarm ->
                        AlarmBanner(alarm) { onAlarmClick(alarm.id) }
                    }
                    items(uiState.cards, key = { it.sensor.id }) { card ->
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
    val sensor = card.sensor
    val tempColor = when (card.status) {
        SensorStatus.OK -> FrigoAccent
        SensorStatus.ALARM -> FrigoCritical
        SensorStatus.OFFLINE -> FrigoTextMuted
    }
    Card(
        onClick = onClick,
        border = BorderStroke(1.dp, if (card.status == SensorStatus.ALARM) FrigoCritical else FrigoOutline),
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(start = 14.dp, end = 14.dp, top = 12.dp, bottom = 10.dp)) {
            CardTitle(sensor.name, card.status)
            Spacer(Modifier.height(8.dp))
            Row(Modifier.height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(56.dp)
                        .border(1.5.dp, FrigoAccent.copy(alpha = 0.6f), CircleShape)
                        .background(FrigoAccent.copy(alpha = 0.06f), CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(sensorIcon(sensor.icon), contentDescription = null, tint = FrigoAccent, modifier = Modifier.size(30.dp))
                }
                Spacer(Modifier.width(14.dp))
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(
                        Formatters.temperatureValue(sensor.current_temperature),
                        color = tempColor,
                        fontWeight = FontWeight.Bold,
                        fontSize = 38.sp,
                        maxLines = 1,
                    )
                    Text(
                        "°C",
                        color = tempColor,
                        fontWeight = FontWeight.Bold,
                        fontSize = 20.sp,
                        modifier = Modifier.padding(bottom = 7.dp, start = 2.dp),
                    )
                }
                Spacer(Modifier.width(10.dp))
                // 24 h min / average / max — colour says which is which.
                StatDivider()
                Stat(card.stats?.min, FrigoMin, Modifier.weight(1f))
                StatDivider()
                Stat(card.stats?.avg, FrigoOk, Modifier.weight(1f))
                StatDivider()
                Stat(card.stats?.max, FrigoCritical, Modifier.weight(1f))
            }
            Spacer(Modifier.height(14.dp))
            CardChart(card.history, Modifier.fillMaxWidth().height(170.dp))
        }
    }
}

/** "——  CHŁODNIA  ——"; a non-OK status is appended in its own colour. */
@Composable
private fun CardTitle(name: String, status: SensorStatus) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        HorizontalDivider(Modifier.weight(1f).padding(start = 40.dp, end = 12.dp), color = FrigoAccent)
        Text(name.uppercase(), color = FrigoTextMuted, fontSize = 16.sp, letterSpacing = 1.sp, maxLines = 1)
        if (status != SensorStatus.OK) {
            Text(
                " · ${status.name}",
                color = if (status == SensorStatus.ALARM) FrigoCritical else FrigoTextMuted,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
            )
        }
        HorizontalDivider(Modifier.weight(1f).padding(start = 12.dp, end = 40.dp), color = FrigoAccent)
    }
}

@Composable
private fun StatDivider() {
    VerticalDivider(Modifier.fillMaxHeight().padding(vertical = 6.dp), color = FrigoOutline)
}

@Composable
private fun Stat(value: Double?, color: Color, modifier: Modifier = Modifier) {
    Text(
        Formatters.temperature(value),
        color = color,
        fontSize = 17.sp,
        fontWeight = FontWeight.SemiBold,
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
    val labelStyle = TextStyle(fontSize = 12.sp, color = FrigoTextMuted)
    Canvas(modifier) {
        if (points.size < 2) return@Canvas
        val now = Instant.now()
        val tStart = now.minus(24, ChronoUnit.HOURS).toEpochMilli()
        val tSpan = (now.toEpochMilli() - tStart).toFloat()
        val (lo, step) = cardAxis(points.minOf { it.value }, points.maxOf { it.value })
        val hi = lo + 2 * step

        val leftPad = 44.dp.toPx()
        val bottomPad = 20.dp.toPx()
        val topPad = 6.dp.toPx()
        val chartW = size.width - leftPad
        val chartH = size.height - bottomPad - topPad
        fun x(t: Instant) = leftPad + ((t.toEpochMilli() - tStart) / tSpan).coerceIn(0f, 1f) * chartW
        fun y(v: Double) = topPad + ((hi - v) / (hi - lo)).toFloat() * chartH

        // Degree axis + horizontal grid
        for (i in 0..2) {
            val v = lo + i * step
            val yy = y(v.toDouble())
            drawLine(FrigoOutline, Offset(leftPad, yy), Offset(size.width, yy), 1f)
            val label = textMeasurer.measure("$v°C", labelStyle)
            drawText(label, topLeft = Offset(leftPad - label.size.width - 6.dp.toPx(), yy - label.size.height / 2))
        }
        drawLine(FrigoTextMuted, Offset(leftPad, topPad), Offset(leftPad, topPad + chartH), 1.5f)

        // Time axis + vertical grid every 4 h
        hourTicks(now).forEach { t ->
            val xx = x(t)
            drawLine(FrigoOutline, Offset(xx, topPad), Offset(xx, topPad + chartH), 1f)
            val label = textMeasurer.measure(t.atZone(ZoneId.systemDefault()).format(hourFormat), labelStyle)
            val lx = (xx - label.size.width / 2).coerceIn(leftPad - 6.dp.toPx(), size.width - label.size.width)
            drawText(label, topLeft = Offset(lx, size.height - label.size.height))
        }

        val visible = points.filter { it.time.toEpochMilli() >= tStart }
        if (visible.size < 2) return@Canvas
        val line = Path()
        visible.forEachIndexed { i, p -> if (i == 0) line.moveTo(x(p.time), y(p.value)) else line.lineTo(x(p.time), y(p.value)) }
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
        drawPath(line, FrigoAccent, style = Stroke(width = 1.5.dp.toPx(), join = StrokeJoin.Round))
    }
}
