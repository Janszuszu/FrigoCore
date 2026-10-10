package pl.frigocore.service.ui.dashboard

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.R
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.AlarmType
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.MessageState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.common.StatusChip
import pl.frigocore.service.permissions.AlarmPermissions
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoOk
import pl.frigocore.service.ui.theme.FrigoWarning

@Composable
fun DashboardScreen(
    isTechnician: Boolean,
    onAlarmClick: (String) -> Unit,
    viewModel: DashboardViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible { viewModel.refresh() }
    val context = LocalContext.current
    var notificationsEnabled by remember { mutableStateOf(AlarmPermissions.notificationsEnabled(context)) }
    var fullScreenIntentAllowed by remember { mutableStateOf(AlarmPermissions.canUseFullScreenIntent(context)) }
    var showClearConfirm by remember { mutableStateOf(false) }
    // Both settings screens are launched for a result purely so returning
    // from them (technician flips the toggle, taps back) re-checks state —
    // the result code itself carries no information.
    val recheckPermissions = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        notificationsEnabled = AlarmPermissions.notificationsEnabled(context)
        fullScreenIntentAllowed = AlarmPermissions.canUseFullScreenIntent(context)
    }

    Column(modifier = Modifier.fillMaxSize()) {
        if (!notificationsEnabled) {
            PermissionWarningBanner(
                text = stringResource(R.string.permission_notifications_warning),
                onFix = { recheckPermissions.launch(AlarmPermissions.appNotificationSettingsIntent(context)) },
            )
        }
        // Only technicians get the full-screen alarm screen; owners receive
        // ordinary notifications, so the permission is irrelevant to them.
        if (isTechnician && !fullScreenIntentAllowed) {
            PermissionWarningBanner(
                text = stringResource(R.string.permission_full_screen_warning),
                onFix = { recheckPermissions.launch(AlarmPermissions.fullScreenIntentSettingsIntent(context)) },
            )
        }
        Box(modifier = Modifier.weight(1f)) {
            when {
                uiState.isLoading && uiState.alarms.isEmpty() -> LoadingState()
                uiState.error != null && uiState.alarms.isEmpty() -> MessageState(uiState.error.orEmpty(), viewModel::refresh)
                uiState.isEmpty -> MessageState(stringResource(R.string.dashboard_empty))
                else -> {
                    val activeTitle = stringResource(R.string.dashboard_section_active)
                    val acknowledgedTitle = stringResource(R.string.dashboard_section_acknowledged)
                    val enRouteTitle = stringResource(R.string.dashboard_section_en_route)
                    val recentTitle = stringResource(R.string.dashboard_section_recent)
                    val clearLabel = stringResource(R.string.dashboard_clear_history)
                    LazyColumn(modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
                        section(activeTitle, uiState.active, FrigoCritical, onAlarmClick)
                        section(acknowledgedTitle, uiState.acknowledged, FrigoWarning, onAlarmClick)
                        section(enRouteTitle, uiState.enRoute, FrigoWarning, onAlarmClick)
                        // Clearing hides history for everyone, so owners don't get it.
                        section(
                            recentTitle, uiState.recent, FrigoOk, onAlarmClick,
                            actionLabel = clearLabel.takeIf { isTechnician },
                            actionEnabled = !uiState.isClearingHistory,
                            onAction = { showClearConfirm = true },
                        )
                    }
                }
            }
        }
    }

    if (showClearConfirm) {
        AlertDialog(
            onDismissRequest = { showClearConfirm = false },
            title = { Text(stringResource(R.string.dashboard_clear_history_title)) },
            text = { Text(stringResource(R.string.dashboard_clear_history_body)) },
            confirmButton = {
                TextButton(onClick = {
                    showClearConfirm = false
                    viewModel.clearHistory()
                }) { Text(stringResource(R.string.dashboard_clear_history_confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { showClearConfirm = false }) {
                    Text(stringResource(R.string.dashboard_clear_history_cancel))
                }
            },
        )
    }

    val clearResult = uiState.clearHistoryResult
    LaunchedEffect(clearResult) {
        if (clearResult == null) return@LaunchedEffect
        val message = when (clearResult) {
            is ApiResult.Success -> context.getString(R.string.dashboard_clear_history_done, clearResult.data)
            is ApiResult.Error -> clearResult.message
        }
        Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
        viewModel.clearHistoryResultShown()
    }
}

@Composable
private fun PermissionWarningBanner(text: String, onFix: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(FrigoWarning)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(text = text, color = Color.White, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
        TextButton(onClick = onFix) {
            Text(text = stringResource(R.string.permission_open_settings), color = Color.White, fontWeight = FontWeight.Bold)
        }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.section(
    title: String,
    alarms: List<AlarmResponse>,
    accentColor: Color,
    onAlarmClick: (String) -> Unit,
    actionLabel: String? = null,
    actionEnabled: Boolean = true,
    onAction: () -> Unit = {},
) {
    if (alarms.isEmpty()) return
    item {
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
            )
            if (actionLabel != null) {
                TextButton(onClick = onAction, enabled = actionEnabled) { Text(text = actionLabel) }
            }
        }
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
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = Formatters.alarmType(alarm.alarm_type, alarm.sensor_kind), fontWeight = FontWeight.Bold)
                Text(
                    text = listOf(alarm.object_name, alarm.sensor_name).filter { it.isNotBlank() }.joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    text = Formatters.dateTime(alarm.detected_at) +
                        (alarm.trigger_value?.takeIf { alarm.alarm_type != AlarmType.OFFLINE }?.let { " · ${Formatters.reading(it, alarm.sensor_unit)}" } ?: ""),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            StatusChip(Formatters.alarmStatus(alarm.status), accentColor)
        }
    }
}
