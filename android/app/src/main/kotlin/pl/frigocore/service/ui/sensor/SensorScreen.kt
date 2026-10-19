package pl.frigocore.service.ui.sensor

import pl.frigocore.service.ui.theme.TabularNumbers
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.pm.ActivityInfo
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
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
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
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
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.Dp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoBackground
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoTextMuted

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
        // Header: name and the shown day on the left, pager, range and close on the right.
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            val window = uiState.window
            Text(
                uiState.sensor?.name.orEmpty().uppercase(),
                color = FrigoAccent,
                fontSize = 18.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false),
            )
            Spacer(Modifier.width(28.dp))
            Text(
                dayHeading(window?.first ?: java.time.Instant.now()),
                color = FrigoAccent,
                fontSize = 16.sp,
                maxLines = 1,
                style = TabularNumbers,
            )
            Spacer(Modifier.weight(1f))
            if (window != null) {
                PagePager(uiState.range, uiState.pageOffset, window, viewModel::shiftPage)
                Spacer(Modifier.width(16.dp))
            }
            RangePicker(uiState.range, viewModel::selectRange)
            Spacer(Modifier.width(10.dp))
            Box(
                Modifier
                    .size(40.dp)
                    .clickable(onClick = onClose),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Filled.Close, contentDescription = "Zamknij", tint = FrigoTextMuted)
            }
        }

        // Value-axis zoom outlives page and range switches; a double tap on the chart clears it.
        var yZoom by remember { mutableStateOf<Pair<Double, Double>?>(null) }
        val onSwipePage: ((Int) -> Unit)? = if (uiState.window != null) viewModel::shiftPage else null
        val limits = uiState.limits
        Box(Modifier.weight(1f).fillMaxWidth().padding(top = 8.dp), contentAlignment = Alignment.Center) {
            when {
                uiState.isLoadingHistory -> CircularProgressIndicator()
                // An empty page still pages, or a gap in the data would be a dead end.
                uiState.points.size < 2 -> Box(
                    Modifier.fillMaxSize().swipePages(onSwipePage, 60.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(uiState.error ?: "Brak odczytów w tym okresie", color = FrigoTextMuted)
                }
                else -> TemperatureChart(
                    uiState.points,
                    showDates = uiState.range == HistoryRange.D7,
                    unit = uiState.sensor?.unit ?: "°C",
                    window = uiState.window,
                    xLabels = uiState.window?.let { pageAxisLabels(uiState.range, it) },
                    yBounds = normalBandBounds(limits?.low, limits?.high),
                    limits = listOfNotNull(limits?.low, limits?.high),
                    onSwipePage = onSwipePage,
                    yZoom = yZoom,
                    onYZoom = { yZoom = it },
                    modifier = Modifier.fillMaxSize(),
                )
            }
        }

        // MIN / AVG / MAX under the chart, aligned with the plot's left edge.
        val unit = uiState.sensor?.unit ?: "°C"
        if (!Formatters.isStateKind(uiState.sensor?.kind)) {
            Row(Modifier.padding(start = 4.dp, top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                StatLabel("MIN", uiState.min, unit)
                Separator()
                StatLabel("AVG", uiState.avg, unit)
                Separator()
                StatLabel("MAX", uiState.max, unit)
            }
        }
    }
}

/** Horizontal drag of at least [distance] pages the window: left = +1, right = -1. */
private fun Modifier.swipePages(onSwipePage: ((Int) -> Unit)?, distance: Dp): Modifier =
    if (onSwipePage == null) this else pointerInput(onSwipePage) {
        var dx = 0f
        detectHorizontalDragGestures(
            onDragStart = { dx = 0f },
            onDragEnd = {
                if (dx <= -distance.toPx()) onSwipePage(1)
                else if (dx >= distance.toPx()) onSwipePage(-1)
            },
        ) { _, amount -> dx += amount }
    }

private val headingFormat = java.time.format.DateTimeFormatter.ofPattern("EEEE, dd.MM.yyyy", java.util.Locale.forLanguageTag("pl"))

/** "Poniedziałek, 19.10.2026" — the day the chart shows. */
private fun dayHeading(instant: java.time.Instant): String =
    instant.atZone(java.time.ZoneId.systemDefault()).format(headingFormat).replaceFirstChar { it.uppercase() }

/** "‹ Dziś ›" / "‹ 12:00–18:00 ›" switcher of a paged range; the future is out of reach. */
@Composable
private fun PagePager(range: HistoryRange, pageOffset: Int, window: Pair<java.time.Instant, java.time.Instant>, onShift: (Int) -> Unit) {
    val label = when {
        range != HistoryRange.H24 -> pageAxisLabels(HistoryRange.H6, window).let { "${it.first()}–${it.last()}" }
        pageOffset == 0 -> "Dziś"
        pageOffset == -1 -> "Wczoraj"
        else -> Formatters.shortDate(window.first)
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            Icons.AutoMirrored.Filled.KeyboardArrowLeft,
            contentDescription = "Wstecz",
            tint = FrigoAccent,
            modifier = Modifier.size(40.dp).clickable { onShift(-1) }.padding(6.dp),
        )
        Text(label, color = FrigoAccent, fontSize = 18.sp, style = TabularNumbers, modifier = Modifier.padding(horizontal = 12.dp))
        Icon(
            Icons.AutoMirrored.Filled.KeyboardArrowRight,
            contentDescription = "Dalej",
            tint = if (pageOffset < 0) FrigoAccent else FrigoOutline,
            modifier = Modifier.size(40.dp).clickable(enabled = pageOffset < 0) { onShift(1) }.padding(6.dp),
        )
    }
}

@Composable
private fun StatLabel(label: String, value: Double?, unit: String) {
    Text(label, color = FrigoTextMuted, fontSize = 15.sp)
    Spacer(Modifier.width(8.dp))
    Text(Formatters.reading(value, unit), color = FrigoAccent, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, style = TabularNumbers)
}

@Composable
private fun Separator() {
    Text("|", color = FrigoOutline, modifier = Modifier.padding(horizontal = 16.dp))
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
            Text(selected.label, color = FrigoAccent, fontSize = 18.sp)
            Spacer(Modifier.width(8.dp))
            Icon(Icons.Filled.KeyboardArrowDown, contentDescription = "Zakres", tint = FrigoAccent)
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
