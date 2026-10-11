package pl.frigocore.service.ui.receivers

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.key
import androidx.compose.ui.draw.clip
import pl.frigocore.service.ui.overview.TempStats
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.material.icons.automirrored.outlined.HelpOutline
import androidx.compose.material.icons.outlined.AcUnit
import androidx.compose.material.icons.outlined.Timer
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.data.model.ReceiverResponse
import pl.frigocore.service.data.model.ReceiverState
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.common.quietClickable
import pl.frigocore.service.ui.overview.CardChart
import pl.frigocore.service.ui.overview.Stat
import pl.frigocore.service.ui.overview.StatDivider
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoMax
import pl.frigocore.service.ui.theme.FrigoOk
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import pl.frigocore.service.ui.theme.TabularNumbers
import kotlinx.coroutines.delay
import java.time.Duration
import java.time.Instant

/** Urządzenia → Odbiorniki: one receiver per page, the next one a swipe
 * away, with dots for where you are. Each page is the chamber on top and
 * its evaporator below. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun ReceiversScreen(
    onOpenChart: (objectId: String, sensorId: String, name: String) -> Unit,
    fallback: @Composable () -> Unit,
    viewModel: ReceiversViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible { viewModel.refresh() }
    // Ticks the running stopwatch between 30 s polls.
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            now = Instant.now()
            delay(1_000)
        }
    }

    when {
        uiState.isLoading && uiState.cards.isEmpty() -> LoadingState()
        // Nothing configured for this object yet — keep showing its sensors.
        uiState.cards.isEmpty() -> fallback()
        // Another object starts again on its first receiver.
        else -> key(uiState.objectId) {
            val pagerState = rememberPagerState { uiState.cards.size }
            Column(Modifier.fillMaxSize()) {
                HorizontalPager(
                    state = pagerState,
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    contentPadding = PaddingValues(horizontal = 12.dp),
                    pageSpacing = 12.dp,
                    key = { uiState.cards.getOrNull(it)?.receiver?.id ?: it },
                ) { page ->
                    val card = uiState.cards.getOrNull(page) ?: return@HorizontalPager
                    ReceiverPage(
                        card,
                        elapsedSinceFetch = Duration.between(uiState.fetchedAt, now).seconds.coerceAtLeast(0),
                        onOpenChart = { sensorId, name -> onOpenChart(card.receiver.object_id, sensorId, name) },
                        modifier = Modifier.fillMaxSize().padding(vertical = 10.dp),
                    )
                }
                if (uiState.cards.size > 1) PageDots(uiState.cards.size, pagerState.currentPage)
            }
        }
    }
}

@Composable
private fun PageDots(count: Int, current: Int) {
    Row(
        Modifier.fillMaxWidth().padding(bottom = 8.dp),
        horizontalArrangement = Arrangement.Center,
    ) {
        repeat(count) { i ->
            Box(
                Modifier
                    .padding(horizontal = 4.dp)
                    .size(if (i == current) 8.dp else 6.dp)
                    .clip(CircleShape)
                    .background(if (i == current) FrigoAccent else FrigoTextMuted.copy(alpha = 0.5f)),
            )
        }
    }
}

private data class StateLook(val label: String, val icon: ImageVector, val color: Color)

private fun stateLook(state: String): StateLook = when (state) {
    ReceiverState.COOLING -> StateLook("Chłodzenie", Icons.Outlined.AcUnit, FrigoAccent)
    ReceiverState.IDLE -> StateLook("Postój", Icons.Outlined.Timer, FrigoOk)
    ReceiverState.DEFROST -> StateLook("Odszranianie", Icons.Outlined.WbSunny, FrigoMax)
    else -> StateLook("Nieznany", Icons.AutoMirrored.Outlined.HelpOutline, FrigoTextMuted)
}

private val AlarmLook = StateLook("Alarm", Icons.Outlined.WarningAmber, FrigoCritical)

/** Stopwatch reading: "4:12", or "1:07:40" past an hour; "--:--" when unknown. */
internal fun stopwatch(seconds: Long?): String {
    if (seconds == null) return "--:--"
    val h = seconds / 3600
    val m = (seconds % 3600) / 60
    val s = seconds % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%d:%02d".format(m, s)
}

/** The chamber on top — name on the left, state icon in the middle,
 * temperature on the right, the 24 h chart and the 24 h min / average / max;
 * then the evaporator the same way; the cycle stopwatches at the very bottom,
 * once for the whole receiver. Everything takes the
 * state colour (blue cooling, green idle, orange defrost, red alarm). Tapping
 * a chart opens it full screen. */
@Composable
private fun ReceiverPage(
    card: ReceiverCard,
    elapsedSinceFetch: Long,
    onOpenChart: (sensorId: String, name: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val receiver = card.receiver
    val look = if (card.alarm) AlarmLook else stateLook(receiver.state)
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, (if (card.alarm) FrigoCritical else FrigoAccent).copy(alpha = 0.35f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
        modifier = modifier,
    ) {
        Column(Modifier.fillMaxSize().padding(horizontal = 14.dp, vertical = 12.dp)) {
            SectionHead(receiver.name, receiver.chamber_temperature, look.color) { StateIcon(look) }
            Spacer(Modifier.height(6.dp))
            CardChart(
                card.chamber,
                look.color,
                Modifier.fillMaxWidth().weight(1f).quietClickable {
                    receiver.chamber_sensor_id?.let { onOpenChart(it, receiver.name) }
                },
            )
            Spacer(Modifier.height(10.dp))
            StatsRow(card.stats)
            if (receiver.evaporator_sensor_id != null) {
                HorizontalDivider(Modifier.padding(vertical = 12.dp), color = look.color.copy(alpha = 0.35f))
                SectionHead("Parownik", receiver.evaporator_temperature, look.color)
                Spacer(Modifier.height(6.dp))
                CardChart(
                    card.evaporator,
                    look.color,
                    Modifier.fillMaxWidth().weight(1f).quietClickable {
                        receiver.evaporator_sensor_id?.let { onOpenChart(it, "${receiver.name} — parownik") }
                    },
                )
                Spacer(Modifier.height(10.dp))
                StatsRow(card.evaporatorStats)
            }
            // A faint line sets the stopwatches apart from the readings above.
            HorizontalDivider(Modifier.padding(top = 12.dp), thickness = 0.5.dp, color = FrigoTextMuted.copy(alpha = 0.3f))
            Stopwatches(receiver, elapsedSinceFetch)
        }
    }
}

/** Name on the left, current temperature on the right and, when given,
 * [badge] exactly in the middle — both sides take equal width. */
@Composable
private fun SectionHead(name: String, temperature: Double?, color: Color, badge: (@Composable () -> Unit)? = null) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            name.uppercase(),
            color = color,
            fontSize = 17.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        if (badge != null) {
            Box(Modifier.padding(horizontal = 8.dp)) { badge() }
        }
        Text(
            Formatters.temperature(temperature),
            color = color,
            fontSize = 26.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            style = TabularNumbers,
            textAlign = TextAlign.End,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun StatsRow(stats: TempStats?) {
    Row(Modifier.height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
        Stat("MIN", stats?.min, "°C", Modifier.weight(1f))
        StatDivider()
        Stat("ŚREDNIA", stats?.avg, "°C", Modifier.weight(1f))
        StatDivider()
        Stat("MAX", stats?.max, "°C", Modifier.weight(1f))
    }
}

/** The state as a bare icon in its colour — no frame, no label. */
@Composable
private fun StateIcon(look: StateLook) {
    Icon(look.icon, contentDescription = look.label, tint = look.color, modifier = Modifier.size(26.dp))
}

/** Idle in the stopwatch row: a pale ice blue beside the brand blue of
 * cooling (the user wanted shades of blue there, not green). */
private val IdleBlue = Color(0xFF9ADCF7)

/** The refrigeration cycle on one line with a single stopwatch icon in
 * the exact middle, brand blue while cooling and pale blue while idle. Left of it the
 * cooling time (cut-in to cut-out) with the cut-out temperature, right of it
 * the idle time with the cut-in temperature, both in brackets. The running time counts on in
 * full colour; the other keeps its last run, dimmed. Both halves take equal
 * width, so the icon never moves and growing times push outwards. */
@Composable
private fun Stopwatches(receiver: ReceiverResponse, elapsedSinceFetch: Long) {
    val phase = receiver.cycle_phase
    val cooling = phase == "cooling"
    val idle = phase == "idle"
    fun running(seconds: Long?, isRunning: Boolean) = if (isRunning && seconds != null) seconds + elapsedSinceFetch else seconds
    fun tint(color: Color, active: Boolean) = if (active) color else color.copy(alpha = 0.45f)
    val iconTint = when {
        cooling -> FrigoAccent
        idle -> IdleBlue
        else -> FrigoTextMuted
    }
    Row(Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
            receiver.cut_out?.let { Threshold(it, FrigoAccent) }
            Spacer(Modifier.width(8.dp))
            CycleTime(running(receiver.cooling_seconds, cooling), tint(FrigoAccent, cooling))
        }
        Icon(
            Icons.Outlined.Timer,
            contentDescription = if (cooling) "Chłodzenie" else if (idle) "Postój" else null,
            tint = iconTint,
            modifier = Modifier.padding(horizontal = 10.dp).size(22.dp),
        )
        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.Start, verticalAlignment = Alignment.CenterVertically) {
            CycleTime(running(receiver.idle_seconds, idle), tint(IdleBlue, idle))
            Spacer(Modifier.width(8.dp))
            receiver.cut_in?.let { Threshold(it, IdleBlue) }
        }
    }
}

@Composable
private fun CycleTime(seconds: Long?, color: Color) {
    Text(stopwatch(seconds), color = color, fontSize = 19.sp, fontWeight = FontWeight.Bold, maxLines = 1, style = TabularNumbers)
}

/** A cut-out / cut-in temperature beside its time, in brackets, in its colour. */
@Composable
private fun Threshold(value: Double, color: Color) {
    Text(
        "(${Formatters.temperature(value)})",
        color = color.copy(alpha = 0.75f),
        fontSize = 13.sp,
        maxLines = 1,
        style = TabularNumbers,
    )
}
