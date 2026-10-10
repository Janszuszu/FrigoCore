package pl.frigocore.service.ui.sensor

import pl.frigocore.service.ui.theme.TabularNumbers
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.pm.ActivityInfo
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.theme.FrigoBackground
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoOk
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import pl.frigocore.service.ui.theme.FrigoWarning

/** Full-screen landscape chart, the same way the web dashboard presents one:
 * a MIN/AVG/MAX strip with a range picker and a close button over the plot. */
@Composable
fun SensorScreen(onClose: () -> Unit, viewModel: SensorViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible(intervalMillis = 60_000) { viewModel.refresh() }
    FullScreenLandscape()

    Column(
        Modifier
            .fillMaxSize()
            .background(FrigoBackground)
            .padding(horizontal = 16.dp, vertical = 10.dp),
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .background(FrigoSurface, RoundedCornerShape(12.dp))
                .border(BorderStroke(1.dp, FrigoOutline), RoundedCornerShape(12.dp))
                .padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                uiState.sensor?.name.orEmpty(),
                color = FrigoText,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false),
            )
            Spacer(Modifier.width(16.dp))
            val unit = uiState.sensor?.unit ?: "°C"
            StatLabel("MIN", uiState.min, unit, FrigoWarning)
            Separator()
            StatLabel("AVG", uiState.avg, unit, FrigoOk)
            Separator()
            StatLabel("MAX", uiState.max, unit, FrigoCritical)
            Spacer(Modifier.weight(1f))
            RangePicker(uiState.range, viewModel::selectRange)
            Spacer(Modifier.width(10.dp))
            Box(
                Modifier
                    .size(40.dp)
                    .border(1.dp, FrigoOutline, RoundedCornerShape(8.dp))
                    .clickable(onClick = onClose),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Filled.Close, contentDescription = "Zamknij", tint = FrigoText)
            }
        }

        Box(Modifier.weight(1f).fillMaxWidth().padding(top = 8.dp), contentAlignment = Alignment.Center) {
            when {
                uiState.isLoadingHistory -> CircularProgressIndicator()
                uiState.points.size < 2 -> Text(uiState.error ?: "Brak odczytów w tym okresie", color = FrigoTextMuted)
                else -> TemperatureChart(
                    uiState.points,
                    showDates = uiState.range == HistoryRange.D7,
                    unit = uiState.sensor?.unit ?: "°C",
                    modifier = Modifier.fillMaxSize(),
                )
            }
        }
    }
}

@Composable
private fun StatLabel(label: String, value: Double?, unit: String, color: Color) {
    Text(label, color = color, fontWeight = FontWeight.Bold, fontSize = 14.sp)
    Spacer(Modifier.width(6.dp))
    Text(Formatters.reading(value, unit), color = FrigoText, fontSize = 14.sp, style = TabularNumbers)
}

@Composable
private fun Separator() {
    Text("|", color = FrigoOutline, modifier = Modifier.padding(horizontal = 10.dp))
}

@Composable
private fun RangePicker(selected: HistoryRange, onSelect: (HistoryRange) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        Row(
            Modifier
                .border(1.dp, FrigoOutline, RoundedCornerShape(8.dp))
                .clickable { expanded = true }
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(selected.label, color = FrigoText, fontWeight = FontWeight.Bold)
            Icon(Icons.Filled.KeyboardArrowDown, contentDescription = "Zakres", tint = FrigoText)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            HistoryRange.entries.forEach { range ->
                DropdownMenuItem(
                    text = { Text(range.label, fontWeight = if (range == selected) FontWeight.Bold else FontWeight.Normal) },
                    onClick = {
                        expanded = false
                        onSelect(range)
                    },
                )
            }
        }
    }
}

/** Landscape + hidden system bars while the chart is on screen; restored on
 * leaving. Not restored across the rotation-induced recreate itself, or the
 * new activity would start in portrait and bounce back and forth. */
@Composable
private fun FullScreenLandscape() {
    val activity = LocalContext.current.findActivity() ?: return
    DisposableEffect(activity) {
        activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        val insets = WindowCompat.getInsetsController(activity.window, activity.window.decorView)
        insets.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        insets.hide(WindowInsetsCompat.Type.systemBars())
        onDispose {
            if (!activity.isChangingConfigurations) {
                activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
                insets.show(WindowInsetsCompat.Type.systemBars())
            }
        }
    }
}

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}
