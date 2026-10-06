package pl.frigocore.service.ui.objects

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
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
import pl.frigocore.service.ui.common.sensorIcon
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoOk

@Composable
fun ObjectDetailScreen(
    onSensorClick: (SensorResponse) -> Unit,
    onAlarmClick: (String) -> Unit,
    viewModel: ObjectDetailViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible { viewModel.refresh() }

    when {
        uiState.isLoading && uiState.sensors.isEmpty() -> LoadingState()
        uiState.error != null && uiState.sensors.isEmpty() -> MessageState(uiState.error.orEmpty(), viewModel::refresh)
        uiState.sensors.isEmpty() -> MessageState("Ten obiekt nie ma jeszcze czujników.")
        else -> LazyVerticalGrid(
            columns = GridCells.Adaptive(minSize = 160.dp),
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(uiState.openAlarms, key = { "alarm-${it.id}" }, span = { GridItemSpan(maxLineSpan) }) { alarm ->
                OpenAlarmBanner(alarm) { onAlarmClick(alarm.id) }
            }
            items(uiState.sensors, key = { it.id }) { sensor ->
                SensorTile(sensor) { onSensorClick(sensor) }
            }
        }
    }
}

@Composable
private fun OpenAlarmBanner(alarm: AlarmResponse, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        colors = CardDefaults.cardColors(containerColor = FrigoCritical, contentColor = Color.White),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Warning, contentDescription = null)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "${Formatters.alarmType(alarm.alarm_type)}${alarm.sensor_name.takeIf { it.isNotBlank() }?.let { " — $it" } ?: ""}",
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    "${Formatters.alarmStatus(alarm.status)} · ${Formatters.dateTime(alarm.detected_at)}",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun SensorTile(sensor: SensorResponse, onClick: () -> Unit) {
    val online = Formatters.isOnline(sensor)
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    sensorIcon(sensor.icon),
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    sensor.name,
                    style = MaterialTheme.typography.labelLarge,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
            }
            Spacer(Modifier.height(10.dp))
            Text(
                Formatters.temperature(sensor.current_temperature),
                fontSize = 30.sp,
                fontWeight = FontWeight.Bold,
                color = if (online) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(8.dp)
                        .background(if (online) FrigoOk else FrigoCritical, CircleShape),
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    if (online) Formatters.ago(sensor.last_message_at) else "Offline · ${Formatters.ago(sensor.last_message_at)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
