package pl.frigocore.service.ui.sensor

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.common.StatusChip
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoOk

@Composable
fun SensorScreen(viewModel: SensorViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible(intervalMillis = 60_000) { viewModel.refresh() }
    val sensor = uiState.sensor

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                Formatters.temperature(sensor?.current_temperature),
                fontSize = 44.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
            )
            if (sensor != null) {
                val online = Formatters.isOnline(sensor)
                StatusChip(if (online) "Online" else "Offline", if (online) FrigoOk else FrigoCritical)
            }
        }
        Text(
            "Ostatni odczyt: ${Formatters.dateTime(sensor?.last_message_at)} (${Formatters.ago(sensor?.last_message_at)})",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Spacer(Modifier.height(16.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HistoryRange.entries.forEach { range ->
                FilterChip(
                    selected = uiState.range == range,
                    onClick = { viewModel.selectRange(range) },
                    label = { Text(range.label) },
                )
            }
        }

        Spacer(Modifier.height(8.dp))
        Card(modifier = Modifier.fillMaxWidth()) {
            Box(Modifier.padding(12.dp), contentAlignment = Alignment.Center) {
                when {
                    uiState.isLoadingHistory -> Box(Modifier.fillMaxWidth().height(240.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                    uiState.points.size < 2 -> Box(Modifier.fillMaxWidth().height(240.dp), contentAlignment = Alignment.Center) {
                        Text(uiState.error ?: "Brak odczytów w tym okresie", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    else -> TemperatureChart(uiState.points, showDates = uiState.range == HistoryRange.D7)
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatCard("Minimum", Formatters.temperature(uiState.min), Modifier.weight(1f))
            StatCard("Maksimum", Formatters.temperature(uiState.max), Modifier.weight(1f))
        }
    }
}

@Composable
private fun StatCard(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(Modifier.padding(14.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        }
    }
}
