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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.TextUnit
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

/** "Chłodzenie od 18 min · pozostało ok. 12 min do -20,0°C". */
internal fun receiverStatusLine(receiver: ReceiverResponse, now: Instant = Instant.now()): String {
    val parts = mutableListOf(stateLook(receiver.state).label)
    Formatters.parseInstant(receiver.state_since)?.let { since ->
        parts[0] += " od ${duration(Duration.between(since, now))}"
    }
    val minutes = receiver.minutes_to_cut_out
    if (minutes != null && receiver.cut_out != null) {
        parts += "pozostało ok. ${duration(Duration.ofSeconds((minutes * 60).toLong()))} do ${Formatters.temperature(receiver.cut_out)}"
    }
    return parts.joinToString(" · ")
}

private fun duration(d: Duration): String {
    val minutes = d.toMinutes().coerceAtLeast(1)
    return if (minutes < 60) "$minutes min" else "${minutes / 60} h ${minutes % 60} min"
}

/** One line of the card: name, chamber | evaporator temperature, state
 * icon; then the 24 h chart and stats, the readings and chart in the state
 * colour (blue cooling, green idle, orange defrost, red alarm); then the
 * details. Tapping the chart opens it full screen. */
@Composable
private fun ReceiverCardView(card: ReceiverCard, onOpenChart: () -> Unit) {
    val receiver = card.receiver
    val look = if (card.alarm) AlarmLook else stateLook(receiver.state)
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, (if (card.alarm) FrigoCritical else FrigoAccent).copy(alpha = 0.35f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(start = 16.dp, end = 14.dp, top = 12.dp, bottom = 12.dp)) {
            Row(Modifier.height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    receiver.name.uppercase(),
                    color = FrigoText,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                Reading(receiver.chamber_temperature, look.color, 24.sp)
                if (receiver.evaporator_sensor_id != null) {
                    VerticalDivider(
                        Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        thickness = 1.5.dp,
                        color = look.color.copy(alpha = 0.6f),
                    )
                    Reading(receiver.evaporator_temperature, look.color, 20.sp)
                }
                Spacer(Modifier.width(10.dp))
                StateIcon(look)
            }
            Spacer(Modifier.height(10.dp))
            CardChart(
                card.chamber,
                look.color,
                Modifier.fillMaxWidth().height(130.dp).clickable(onClick = onOpenChart),
            )
            Spacer(Modifier.height(10.dp))
            Row(Modifier.height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
                Stat("MIN", card.stats?.min, "°C", Modifier.weight(1f))
                StatDivider()
                Stat("ŚREDNIA", card.stats?.avg, "°C", Modifier.weight(1f))
                StatDivider()
                Stat("MAX", card.stats?.max, "°C", Modifier.weight(1f))
            }
            Details(receiver, card.alarm)
        }
    }
}

@Composable
private fun Reading(value: Double?, color: Color, size: TextUnit) {
    Text(
        Formatters.temperature(value),
        color = color,
        fontSize = size,
        fontWeight = FontWeight.Bold,
        maxLines = 1,
        style = TabularNumbers,
    )
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

/** State, how long, time left, and the controller's working temperatures. */
@Composable
private fun Details(receiver: ReceiverResponse, alarm: Boolean) {
    Column(Modifier.fillMaxWidth().padding(top = 10.dp)) {
        Text(
            (if (alarm) "Alarm · " else "") + receiverStatusLine(receiver),
            color = FrigoTextMuted,
            fontSize = 13.sp,
        )
        if (receiver.cut_in != null || receiver.cut_out != null) {
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp), modifier = Modifier.padding(top = 2.dp)) {
                receiver.cut_in?.let { Text("Załącz. ${Formatters.temperature(it)}", color = FrigoTextMuted, fontSize = 12.sp) }
                receiver.cut_out?.let { Text("Wyłącz. ${Formatters.temperature(it)}", color = FrigoTextMuted, fontSize = 12.sp) }
            }
        }
    }
}
