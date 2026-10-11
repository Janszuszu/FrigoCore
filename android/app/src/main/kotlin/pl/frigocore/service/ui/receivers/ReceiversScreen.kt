package pl.frigocore.service.ui.receivers

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.HelpOutline
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.outlined.AcUnit
import androidx.compose.material.icons.outlined.Timer
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.data.model.ReceiverResponse
import pl.frigocore.service.data.model.ReceiverState
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.PollWhileVisible
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
        else -> LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
            contentPadding = PaddingValues(top = 10.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(uiState.cards, key = { it.receiver.id }) { card ->
                ReceiverCardView(
                    card,
                    elapsedSinceFetch = Duration.between(uiState.fetchedAt, now).seconds.coerceAtLeast(0),
                    onOpenChart = {
                        card.receiver.chamber_sensor_id?.let { onOpenChart(card.receiver.object_id, it, card.receiver.name) }
                    },
                )
            }
        }
    }
}

/** [drip] adds a water drop to the icon — a melting snowflake for defrost. */
private data class StateLook(val label: String, val icon: ImageVector, val color: Color, val drip: Boolean = false)

private fun stateLook(state: String): StateLook = when (state) {
    ReceiverState.COOLING -> StateLook("Chłodzenie", Icons.Outlined.AcUnit, FrigoAccent)
    ReceiverState.IDLE -> StateLook("Postój", Icons.Outlined.Timer, FrigoOk)
    ReceiverState.DEFROST -> StateLook("Odszranianie", Icons.Outlined.AcUnit, FrigoMax, drip = true)
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

/** Top to bottom: the name on the left, with the state icon in the right
 * corner; the leading (chamber) | evaporator temperature, same size, each
 * labelled in small grey; the chart; the cycle stopwatches; the
 * 24 h min / average / max. Readings and chart take the state colour (blue cooling,
 * green idle, orange defrost, red alarm). Tapping the chart opens it full
 * screen. */
@Composable
private fun ReceiverCardView(card: ReceiverCard, elapsedSinceFetch: Long, onOpenChart: () -> Unit) {
    val receiver = card.receiver
    val look = if (card.alarm) AlarmLook else stateLook(receiver.state)
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, (if (card.alarm) FrigoCritical else FrigoAccent).copy(alpha = 0.35f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
            // Name on the left; the state icon keeps its corner.
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterStart) {
                Text(
                    receiver.name.uppercase(),
                    color = FrigoText,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.fillMaxWidth().padding(end = 40.dp),
                )
                Box(Modifier.align(Alignment.CenterEnd)) { StateIcon(look) }
            }
            Spacer(Modifier.height(6.dp))
            Row(
                Modifier.fillMaxWidth().height(IntrinsicSize.Min),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center,
            ) {
                Reading(receiver.chamber_temperature, look.color, "WIODĄCA")
                if (receiver.evaporator_sensor_id != null) {
                    VerticalDivider(
                        Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                        thickness = 1.5.dp,
                        color = look.color.copy(alpha = 0.6f),
                    )
                    Reading(receiver.evaporator_temperature, look.color, "PAROWNIK")
                }
            }
            Spacer(Modifier.height(10.dp))
            CardChart(
                card.chamber,
                look.color,
                Modifier.fillMaxWidth().height(130.dp).clickable(onClick = onOpenChart),
            )
            Stopwatches(receiver, elapsedSinceFetch)
            Spacer(Modifier.height(12.dp))
            Row(Modifier.height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
                Stat("MIN", card.stats?.min, "°C", Modifier.weight(1f))
                StatDivider()
                Stat("ŚREDNIA", card.stats?.avg, "°C", Modifier.weight(1f))
                StatDivider()
                Stat("MAX", card.stats?.max, "°C", Modifier.weight(1f))
            }
        }
    }
}

/** A temperature with what it measures underneath in small grey. */
@Composable
private fun Reading(value: Double?, color: Color, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            Formatters.temperature(value),
            color = color,
            fontSize = 30.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            style = TabularNumbers,
        )
        Text(label, color = FrigoTextMuted, fontSize = 11.sp, letterSpacing = 0.5.sp, maxLines = 1)
    }
}

/** The state as a bare icon in its colour — no frame, no label. */
@Composable
private fun StateIcon(look: StateLook) {
    Box(Modifier.size(30.dp)) {
        Icon(
            look.icon,
            contentDescription = look.label,
            tint = look.color,
            modifier = Modifier.size(if (look.drip) 24.dp else 30.dp).align(Alignment.TopCenter),
        )
        if (look.drip) {
            Icon(
                Icons.Filled.WaterDrop,
                contentDescription = null,
                tint = look.color,
                modifier = Modifier.size(11.dp).align(Alignment.BottomCenter),
            )
        }
    }
}

/** Two stopwatches for the refrigeration cycle: blue times the cooling
 * (from cut-in to cut-out), green the idle that follows. The running one
 * counts on, the other keeps its last run, dimmed, until its turn. Each
 * phase's end temperature sits on its outer side, unlabelled: the cut-out
 * before the blue one, the cut-in after the green one. */
@Composable
private fun Stopwatches(receiver: ReceiverResponse, elapsedSinceFetch: Long) {
    val phase = receiver.cycle_phase
    fun running(seconds: Long?, isRunning: Boolean) = if (isRunning && seconds != null) seconds + elapsedSinceFetch else seconds
    Row(
        Modifier.fillMaxWidth().padding(top = 12.dp).height(IntrinsicSize.Min),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        receiver.cut_out?.let { Threshold(it, FrigoAccent) }
        Stopwatch(running(receiver.cooling_seconds, phase == "cooling"), FrigoAccent, active = phase == "cooling", label = "Chłodzenie")
        VerticalDivider(Modifier.padding(horizontal = 12.dp, vertical = 2.dp), thickness = 1.5.dp, color = FrigoTextMuted.copy(alpha = 0.5f))
        Stopwatch(running(receiver.idle_seconds, phase == "idle"), FrigoOk, active = phase == "idle", label = "Postój")
        receiver.cut_in?.let { Threshold(it, FrigoOk, before = false) }
    }
}

@Composable
private fun Stopwatch(seconds: Long?, color: Color, active: Boolean, label: String) {
    val tint = if (active) color else color.copy(alpha = 0.45f)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Outlined.Timer, contentDescription = label, tint = tint, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(5.dp))
        Text(stopwatch(seconds), color = tint, fontSize = 19.sp, fontWeight = FontWeight.Bold, maxLines = 1, style = TabularNumbers)
    }
}

/** A cut-out / cut-in temperature beside its stopwatch, in its colour. */
@Composable
private fun Threshold(value: Double, color: Color, before: Boolean = true) {
    Text(
        Formatters.temperature(value),
        color = color.copy(alpha = 0.75f),
        fontSize = 13.sp,
        maxLines = 1,
        style = TabularNumbers,
        modifier = Modifier.padding(start = if (before) 0.dp else 8.dp, end = if (before) 8.dp else 0.dp),
    )
}
