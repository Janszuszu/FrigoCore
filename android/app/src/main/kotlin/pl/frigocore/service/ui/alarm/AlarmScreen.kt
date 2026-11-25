package pl.frigocore.service.ui.alarm

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.frigocore.service.R
import pl.frigocore.service.data.model.AlarmStatus
import pl.frigocore.service.data.model.AlarmType
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoOk

@Composable
fun AlarmScreen(
    uiState: AlarmUiState,
    onAccept: () -> Unit,
    onDismissError: () -> Unit,
    /** False for object owners: they see the alarm, technicians act on it. */
    canAct: Boolean = true,
) {
    val actionInProgress = uiState.actionInFlight != AlarmActionInFlight.NONE

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(FrigoCritical)
            .safeDrawingPadding()
            .padding(20.dp),
        verticalArrangement = Arrangement.Top,
    ) {
        Text(
            text = stringResource(R.string.alarm_critical_label),
            color = Color.White,
            fontSize = 28.sp,
            fontWeight = FontWeight.ExtraBold,
        )

        Spacer(modifier = Modifier.height(4.dp))

        StatusBadge(status = Formatters.alarmStatus(uiState.effectiveStatus))

        Spacer(modifier = Modifier.height(20.dp))

        InfoCard {
            InfoRow("Obiekt", (uiState.alarm?.object_name?.ifBlank { null } ?: uiState.siteName).ifBlank { "—" })
            InfoRow("Typ alarmu", Formatters.alarmType(uiState.alarm?.alarm_type ?: uiState.payloadAlarmType, uiState.alarm?.sensor_kind ?: "temperature"))
            uiState.alarm?.trigger_value?.takeIf {
                uiState.alarm.alarm_type != AlarmType.OFFLINE && !Formatters.isStateKind(uiState.alarm.sensor_kind)
            }?.let {
                InfoRow("Odczyt", Formatters.reading(it, uiState.alarm.sensor_unit))
            }
            InfoRow("Sensor", (uiState.alarm?.sensor_name?.ifBlank { null } ?: uiState.payloadSensorName).ifBlank { "—" })
            InfoRow("Wykryto", Formatters.dateTime(uiState.alarm?.detected_at ?: uiState.payloadCreatedAt))
            InfoRow("Status", Formatters.alarmStatus(uiState.effectiveStatus))
        }

        Spacer(modifier = Modifier.height(24.dp))

        if (uiState.actionError != null) {
            ErrorBanner(message = uiState.actionError, onDismiss = onDismissError)
            Spacer(modifier = Modifier.height(16.dp))
        }

        // One button only: PRZYJĄŁEM. After it the alarm is "serwis w
        // trakcie realizacji" for everyone and closes by itself once the
        // reading is back to normal.
        if (canAct && uiState.effectiveStatus == AlarmStatus.TRIGGERED) {
            Button(
                onClick = onAccept,
                enabled = !actionInProgress,
                colors = ButtonDefaults.buttonColors(containerColor = FrigoOk),
                modifier = Modifier.fillMaxWidth().height(64.dp),
            ) { ActionLabel(stringResource(R.string.action_accept), actionInProgress) }
            return@Column
        }

        Text(
            text = when (uiState.effectiveStatus) {
                AlarmStatus.RESOLVED, AlarmStatus.ARCHIVED -> "Alarm zakończony."
                AlarmStatus.EN_ROUTE, AlarmStatus.ACKNOWLEDGED ->
                    "Serwis w trakcie realizacji. Alarm zamknie się sam, gdy odczyt wróci do normy."
                else -> "Serwis został powiadomiony."
            },
            color = Color.White,
            style = MaterialTheme.typography.titleMedium,
        )
    }
}

@Composable
private fun ActionLabel(text: String, loading: Boolean, color: Color = Color.White) {
    if (loading) {
        CircularProgressIndicator(modifier = Modifier.height(22.dp), strokeWidth = 2.dp, color = color)
    } else {
        Text(text, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = color)
    }
}

@Composable
private fun StatusBadge(status: String) {
    Text(
        text = status.uppercase(),
        color = Color.White,
        modifier = Modifier
            .background(Color.Black.copy(alpha = 0.25f), RoundedCornerShape(6.dp))
            .padding(horizontal = 10.dp, vertical = 4.dp),
        fontWeight = FontWeight.SemiBold,
    )
}

@Composable
private fun InfoCard(content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color.White.copy(alpha = 0.12f), RoundedCornerShape(12.dp))
            .padding(16.dp),
        content = content,
    )
}

@Composable
private fun InfoRow(label: String, value: String) {
    Column(modifier = Modifier.padding(vertical = 6.dp)) {
        Text(text = label, color = Color.White.copy(alpha = 0.75f), fontSize = 13.sp)
        Text(text = value, color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Medium)
    }
    Divider(color = Color.White.copy(alpha = 0.15f))
}

@Composable
private fun ErrorBanner(message: String, onDismiss: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color.Black.copy(alpha = 0.35f), RoundedCornerShape(8.dp))
            .padding(12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text = message, color = Color.White, modifier = Modifier.padding(end = 8.dp))
        Text(
            text = "OK",
            color = Color.White,
            fontWeight = FontWeight.Bold,
            modifier = Modifier
                .padding(start = 8.dp)
                .then(Modifier.clickableNoIndication(onDismiss)),
        )
    }
}

@Composable
private fun Modifier.clickableNoIndication(onClick: () -> Unit): Modifier =
    this.clickable(
        interactionSource = androidx.compose.runtime.remember { MutableInteractionSource() },
        indication = null,
        onClick = onClick,
    )
