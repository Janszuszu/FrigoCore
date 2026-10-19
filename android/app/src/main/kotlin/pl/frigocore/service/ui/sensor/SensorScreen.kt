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
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
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
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoMin
import pl.frigocore.service.ui.theme.FrigoOk
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted

/** Full-screen landscape chart: name and day over the plot with the page
 * switcher and range picker, MIN / ŚREDNIA / MAX with their times under it. */
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
        Header(uiState, viewModel::selectRange, onClose)
        HorizontalDivider(Modifier.padding(top = 8.dp), color = FrigoOutline)

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
                    limits = listOfNotNull(limits?.low, limits?.high),
                    onSwipePage = onSwipePage,
                    yZoom = yZoom,
                    onYZoom = { yZoom = it },
                    modifier = Modifier.fillMaxSize(),
                )
            }
        }

        if (!Formatters.isStateKind(uiState.sensor?.kind)) {
            HorizontalDivider(Modifier.padding(top = 6.dp), color = FrigoOutline)
            StatsFooter(uiState)
        }
    }
}

/** "Komora - mroźnia 1 (czujnik główny)" → "Komora - mroźnia 1" over
 * "Czujnik główny"; a name without a trailing bracket has no subtitle. */
internal fun splitSensorName(name: String): Pair<String, String?> {
    val match = Regex("""^(.*\S)\s*\(([^()]+)\)\s*$""").find(name) ?: return name to null
    return match.groupValues[1] to match.groupValues[2].trim().replaceFirstChar { it.uppercase() }
}

@Composable
private fun Header(
    uiState: SensorUiState,
    onRange: (HistoryRange) -> Unit,
    onClose: () -> Unit,
) {
    val window = uiState.window
    val (title, subtitle) = splitSensorName(uiState.sensor?.name.orEmpty())
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.width(4.dp).height(44.dp).background(FrigoAccent, RoundedCornerShape(2.dp)))
        Spacer(Modifier.width(12.dp))
        // Takes all the room the date and range picker leave; a long name wraps rather than cuts.
        Column(Modifier.weight(1f)) {
            Text(title, color = FrigoText, fontSize = 20.sp, lineHeight = 24.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (subtitle != null) {
                Text(subtitle, color = FrigoTextMuted, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        Spacer(Modifier.width(16.dp))
        Icon(Icons.Outlined.CalendarMonth, contentDescription = null, tint = FrigoTextMuted, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(8.dp))
        // 1H and 6H pages also say which hours they cover: "Poniedziałek, 19.10.2026 · 12:00–18:00".
        val day = dayHeading(window?.first ?: java.time.Instant.now())
        val hours = window?.takeIf { uiState.range == HistoryRange.H1 || uiState.range == HistoryRange.H6 }
            ?.let { pageAxisLabels(HistoryRange.H6, it).let { labels -> " · ${labels.first()}–${labels.last()}" } }
        Text(day + hours.orEmpty(), color = FrigoTextMuted, fontSize = 16.sp, maxLines = 1, style = TabularNumbers)
        Spacer(Modifier.width(24.dp))
        RangePicker(uiState.range, onRange)
        Spacer(Modifier.width(8.dp))
        Box(Modifier.size(40.dp).clickable(onClick = onClose), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.Close, contentDescription = "Zamknij", tint = FrigoTextMuted)
        }
    }
}

/** MIN, ŚREDNIA and MAX side by side, split by thin rules; MIN and MAX also say when. */
@Composable
private fun StatsFooter(uiState: SensorUiState) {
    val unit = uiState.sensor?.unit ?: "°C"
    val withDate = uiState.range == HistoryRange.D7
    fun at(point: ChartPoint?) = point?.time?.let {
        if (withDate) "${Formatters.shortDate(it)} ${Formatters.time(it)}" else Formatters.time(it)
    }
    Row(Modifier.fillMaxWidth().height(52.dp), verticalAlignment = Alignment.CenterVertically) {
        Stat("MIN", uiState.min, unit, FrigoMin, at(uiState.minPoint), Modifier.weight(1f))
        VerticalDivider(Modifier.height(36.dp), color = FrigoOutline)
        Stat("ŚREDNIA", uiState.avg, unit, FrigoOk, null, Modifier.weight(1f))
        VerticalDivider(Modifier.height(36.dp), color = FrigoOutline)
        Stat("MAX", uiState.max, unit, FrigoCritical, at(uiState.maxPoint), Modifier.weight(1f))
    }
}

@Composable
private fun Stat(label: String, value: Double?, unit: String, color: Color, time: String?, modifier: Modifier) {
    Row(modifier, horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = FrigoTextMuted, fontSize = 15.sp)
        Spacer(Modifier.width(16.dp))
        Text(Formatters.reading(value, unit), color = color, fontWeight = FontWeight.SemiBold, fontSize = 28.sp, style = TabularNumbers)
        if (time != null) {
            Spacer(Modifier.width(12.dp))
            Text(time, color = FrigoTextMuted, fontSize = 14.sp, style = TabularNumbers)
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

@Composable
private fun RangePicker(selected: HistoryRange, onSelect: (HistoryRange) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        Row(
            Modifier
                .border(1.dp, FrigoOutline, RoundedCornerShape(12.dp))
                .clickable { expanded = true }
                .padding(horizontal = 16.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(selected.label, color = FrigoAccent, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.width(20.dp))
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
