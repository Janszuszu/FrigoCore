package pl.frigocore.service.ui.common

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AcUnit
import androidx.compose.material.icons.filled.Air
import androidx.compose.material.icons.filled.Compress
import androidx.compose.material.icons.filled.DoorFront
import androidx.compose.material.icons.filled.Kitchen
import androidx.compose.material.icons.filled.MeetingRoom
import androidx.compose.material.icons.filled.Plumbing
import androidx.compose.material.icons.filled.Power
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Thermostat
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material.icons.filled.Whatshot
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay

/** Runs [action] immediately and then every [intervalMillis] while the
 * screen is visible — stops in the background so it never drains battery. */
@Composable
fun PollWhileVisible(intervalMillis: Long = 30_000, action: () -> Unit) {
    val lifecycleOwner = LocalLifecycleOwner.current
    val currentAction by rememberUpdatedState(action)
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                currentAction()
                delay(intervalMillis)
            }
        }
    }
}

/** Maps the backend's sensor icon ids (frontend/src/utils/sensorIcons.ts). */
fun sensorIcon(id: String): ImageVector = when (id) {
    "evaporator", "snowflake" -> Icons.Filled.AcUnit
    "condenser" -> Icons.Filled.Whatshot
    "compressor" -> Icons.Filled.Compress
    "fan" -> Icons.Filled.Air
    "room" -> Icons.Filled.MeetingRoom
    "outdoor" -> Icons.Filled.WbSunny
    "cabinet" -> Icons.Filled.Kitchen
    "pipe" -> Icons.Filled.Plumbing
    "pressure" -> Icons.Filled.Speed
    "door" -> Icons.Filled.DoorFront
    "power" -> Icons.Filled.Power
    "humidity" -> Icons.Filled.WaterDrop
    else -> Icons.Filled.Thermostat
}

@Composable
fun StatusChip(text: String, color: Color, modifier: Modifier = Modifier) {
    Text(
        text = text,
        color = Color.White,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.SemiBold,
        modifier = modifier
            .background(color, RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    )
}

@Composable
fun LoadingState() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
}

@Composable
fun MessageState(text: String, onRetry: (() -> Unit)? = null) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(text = text, textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (onRetry != null) {
            Button(onClick = onRetry, modifier = Modifier.padding(top = 16.dp)) { Text("Spróbuj ponownie") }
        }
    }
}
