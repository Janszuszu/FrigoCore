package pl.frigocore.service.ui.objects

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.outlined.Apartment
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.data.model.ObjectResponse
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.MessageState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.common.StatusChip
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoOk
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoWarning

@Composable
fun ObjectsScreen(
    onObjectClick: (ObjectResponse) -> Unit,
    viewModel: ObjectsViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible { viewModel.refresh() }

    when {
        uiState.isLoading && uiState.objects.isEmpty() -> LoadingState()
        uiState.error != null && uiState.objects.isEmpty() -> MessageState(uiState.error.orEmpty(), viewModel::refresh)
        uiState.objects.isEmpty() -> MessageState("Nie masz jeszcze przypisanych obiektów.\nSkontaktuj się z administratorem.")
        else -> LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(uiState.objects, key = { it.id }) { obj ->
                ObjectCard(obj, uiState.activeAlarmsByObject[obj.id] ?: 0) { onObjectClick(obj) }
            }
        }
    }
}

@Composable
private fun ObjectCard(obj: ObjectResponse, openAlarms: Int, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        border = BorderStroke(1.dp, if (openAlarms > 0) FrigoCritical else FrigoOutline),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Outlined.Apartment,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(32.dp),
            )
            Spacer(Modifier.width(14.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(obj.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                if (obj.description.isNotBlank()) {
                    Text(
                        obj.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Row(modifier = Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    val allOnline = obj.sensor_count > 0 && obj.online_sensor_count == obj.sensor_count
                    StatusChip(
                        "Czujniki ${obj.online_sensor_count}/${obj.sensor_count}",
                        if (allOnline) FrigoOk else FrigoWarning,
                    )
                    if (openAlarms > 0) {
                        StatusChip("Alarmy: $openAlarms", FrigoCritical)
                    }
                }
            }
            Icon(Icons.Filled.ChevronRight, contentDescription = null)
        }
    }
}
