package pl.frigocore.service.ui.overview

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import kotlinx.coroutines.delay
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.ObjectResponse
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.MessageState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.common.sensorIcon
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

@Composable
fun OverviewScreen(
    onSensorClick: (SensorResponse) -> Unit,
    onAlarmClick: (String) -> Unit,
    viewModel: OverviewViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible { viewModel.refresh() }

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        ClockRow()
        ObjectSelector(uiState.objects, uiState.selectedObject, viewModel::selectObject)
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

private val clockFormat = DateTimeFormatter.ofPattern("HH:mm:ss")
private val dateFormat = DateTimeFormatter.ofPattern("d.MM.yyyy")

@Composable
private fun ClockRow() {
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            now = Instant.now()
            delay(1_000)
        }
    }
    val local = now.atZone(ZoneId.systemDefault())
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text("OBIEKT", color = FrigoTextMuted, style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
        Text(local.format(clockFormat), color = FrigoText, fontWeight = FontWeight.Bold, fontSize = 17.sp)
        Text(
            local.format(dateFormat),
            color = FrigoTextMuted,
            style = MaterialTheme.typography.labelLarge,
            modifier = Modifier.weight(1f),
            textAlign = androidx.compose.ui.text.style.TextAlign.End,
        )
    }
}

@Composable
private fun ObjectSelector(objects: List<ObjectResponse>, selected: ObjectResponse?, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .border(1.5.dp, FrigoText.copy(alpha = 0.85f), RoundedCornerShape(10.dp))
                .clickable(enabled = objects.size > 1) { expanded = true }
                .padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                selected?.name ?: "—",
                color = FrigoText,
                fontSize = 17.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            if (objects.size > 1) Icon(Icons.Filled.KeyboardArrowDown, contentDescription = "Wybierz obiekt", tint = FrigoText)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            objects.forEach { obj ->
                DropdownMenuItem(
                    text = { Text(obj.name, fontWeight = if (obj.id == selected?.id) FontWeight.Bold else FontWeight.Normal) },
                    onClick = {
                        expanded = false
                        onSelect(obj.id)
                    },
                )
            }
        }
    }
}

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
    val statusColor = when (card.status) {
        SensorStatus.OK -> FrigoOk
        SensorStatus.ALARM -> FrigoCritical
        SensorStatus.OFFLINE -> FrigoTextMuted
    }
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
        Row(Modifier.height(IntrinsicSize.Min).padding(14.dp)) {
            // Left: icon, name, live reading, status
            Row(Modifier.weight(0.46f)) {
                Box(
                    Modifier
                        .size(44.dp)
                        .border(1.dp, FrigoAccent.copy(alpha = 0.5f), CircleShape)
                        .background(FrigoAccent.copy(alpha = 0.08f), CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(sensorIcon(sensor.icon), contentDescription = null, tint = FrigoAccent, modifier = Modifier.size(24.dp))
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        sensor.name.uppercase(),
                        color = FrigoText,
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(
                            Formatters.temperatureValue(sensor.current_temperature),
                            color = tempColor,
                            fontWeight = FontWeight.Bold,
                            fontSize = 34.sp,
                            maxLines = 1,
                        )
                        Text("°C", color = tempColor, fontWeight = FontWeight.Bold, fontSize = 17.sp, modifier = Modifier.padding(bottom = 5.dp, start = 2.dp))
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(9.dp).background(statusColor, CircleShape))
                        Spacer(Modifier.width(6.dp))
                        Text(card.status.name, color = statusColor, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    }
                    Text(Formatters.ago(sensor.last_message_at), color = FrigoTextMuted, fontSize = 12.sp)
                }
            }
            VerticalDivider(Modifier.fillMaxHeight().padding(horizontal = 10.dp), color = FrigoOutline)
            // Right: 24 h stats + sparkline
            Column(Modifier.weight(0.54f)) {
                Row(Modifier.fillMaxWidth()) {
                    Stat("MIN 24h", card.stats?.min, FrigoMin, Modifier.weight(1f))
                    Stat("ŚREDNIA 24h", card.stats?.avg, FrigoText, Modifier.weight(1.2f))
                    Stat("MAX 24h", card.stats?.max, FrigoCritical, Modifier.weight(1f))
                }
                HorizontalDivider(Modifier.padding(vertical = 8.dp), color = FrigoOutline)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Sparkline(card.spark, Modifier.weight(1f).height(44.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("24h", color = FrigoText, fontSize = 12.sp)
                    Icon(Icons.Filled.ChevronRight, contentDescription = "Wykres", tint = FrigoText, modifier = Modifier.size(18.dp))
                }
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: Double?, color: Color, modifier: Modifier = Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, color = FrigoTextMuted, fontSize = 10.sp, maxLines = 1)
        Text(Formatters.temperature(value), color = color, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
    }
}

@Composable
private fun Sparkline(values: List<Double>, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        if (values.size < 2) return@Canvas
        val min = values.min()
        val span = (values.max() - min).coerceAtLeast(0.5)
        val stepX = size.width / (values.size - 1)
        fun y(v: Double) = (size.height * (1 - (v - min) / span)).toFloat().coerceIn(1f, size.height - 1f)
        val line = Path()
        values.forEachIndexed { i, v -> if (i == 0) line.moveTo(0f, y(v)) else line.lineTo(i * stepX, y(v)) }
        val fill = Path().apply {
            addPath(line)
            lineTo(size.width, size.height)
            lineTo(0f, size.height)
            close()
        }
        drawPath(fill, Brush.verticalGradient(listOf(FrigoAccent.copy(alpha = 0.45f), FrigoAccent.copy(alpha = 0.05f))))
        drawPath(line, FrigoAccent, style = Stroke(width = 1.5.dp.toPx(), join = StrokeJoin.Round))
    }
}
