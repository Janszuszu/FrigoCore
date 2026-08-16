package pl.frigocore.service.ui.dashboard

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.R
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoOk
import pl.frigocore.service.ui.theme.FrigoWarning

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    onAlarmClick: (String) -> Unit,
    onLoggedOut: () -> Unit,
    viewModel: DashboardViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.dashboard_title)) },
                actions = {
                    IconButton(onClick = viewModel::refresh) {
                        Icon(Icons.Default.Refresh, contentDescription = "Odśwież")
                    }
                    IconButton(onClick = { viewModel.logout(onLoggedOut) }) {
                        Icon(Icons.Default.Logout, contentDescription = stringResource(R.string.dashboard_logout))
                    }
                },
            )
        },
    ) { padding: PaddingValues ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            when {
                uiState.isLoading && uiState.alarms.isEmpty() -> {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                }
                uiState.error != null && uiState.alarms.isEmpty() -> {
                    Text(
                        text = uiState.error.orEmpty(),
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.align(Alignment.Center).padding(24.dp),
                    )
                }
                uiState.alarms.isEmpty() -> {
                    Text(
                        text = stringResource(R.string.dashboard_empty),
                        modifier = Modifier.align(Alignment.Center),
                    )
                }
                else -> {
                    val activeTitle = stringResource(R.string.dashboard_section_active)
                    val acknowledgedTitle = stringResource(R.string.dashboard_section_acknowledged)
                    val enRouteTitle = stringResource(R.string.dashboard_section_en_route)
                    val recentTitle = stringResource(R.string.dashboard_section_recent)
                    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
                        section(activeTitle, uiState.active, FrigoCritical, onAlarmClick)
                        section(acknowledgedTitle, uiState.acknowledged, FrigoWarning, onAlarmClick)
                        section(enRouteTitle, uiState.enRoute, FrigoWarning, onAlarmClick)
                        section(recentTitle, uiState.recent, FrigoOk, onAlarmClick)
                    }
                }
            }
        }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.section(
    title: String,
    alarms: List<AlarmResponse>,
    accentColor: Color,
    onAlarmClick: (String) -> Unit,
) {
    if (alarms.isEmpty()) return
    item {
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(top = 16.dp, bottom = 8.dp),
        )
    }
    items(alarms, key = { it.id }) { alarm ->
        AlarmRow(alarm = alarm, accentColor = accentColor, onClick = { onAlarmClick(alarm.id) })
    }
}

@Composable
private fun AlarmRow(alarm: AlarmResponse, accentColor: Color, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        shape = RoundedCornerShape(10.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text(text = alarm.alarm_type.uppercase(), fontWeight = FontWeight.Bold)
                Text(text = alarm.description, style = MaterialTheme.typography.bodySmall)
                Text(text = alarm.detected_at, style = MaterialTheme.typography.labelSmall)
            }
            Box(
                modifier = Modifier
                    .background(accentColor, RoundedCornerShape(6.dp))
                    .padding(horizontal = 8.dp, vertical = 4.dp),
            ) {
                Text(text = alarm.status.uppercase(), color = Color.White, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}
