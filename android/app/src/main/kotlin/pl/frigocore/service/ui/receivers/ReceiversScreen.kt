package pl.frigocore.service.ui.receivers

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.HelpOutline
import androidx.compose.material.icons.outlined.AcUnit
import androidx.compose.material.icons.outlined.ModeFanOff
import androidx.compose.material.icons.outlined.Whatshot
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import pl.frigocore.service.ui.theme.FrigoMax
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import pl.frigocore.service.ui.theme.TabularNumbers
import java.time.Duration
import java.time.Instant

/** Evaporator trace on a receiver's chart. */
private val EvaporatorColor = Color(0xFFA78BFA)

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

private data class StateLook(val label: String, val icon: ImageVector, val color: Color)

private fun stateLook(state: String): StateLook = when (state) {
    ReceiverState.COOLING -> StateLook("Chłodzenie", Icons.Outlined.AcUnit, FrigoAccent)
    ReceiverState.IDLE -> StateLook("Postój", Icons.Outlined.ModeFanOff, FrigoText)
    ReceiverState.DEFROST -> StateLook("Odszranianie", Icons.Outlined.Whatshot, FrigoMax)
    else -> StateLook("Nieznany", Icons.AutoMirrored.Outlined.HelpOutline, FrigoTextMuted)
}

/** "Chłodzenie od 18 min · pozostało ok. 12 min do -20,0°C". */
internal fun receiverStatusLine(receiver: ReceiverResponse, now: Instant = Instant.now()): String {
    val parts = mutableListOf(stateLook(receiver.state).label)
    Formatters.parseInstant(receiver.state_since)?.let { since ->
        parts[0] += " od ${duration(Duration.between(since, now))}"
    }
    val minutes = receiver.minutes_to_setpoint
    if (minutes != null && receiver.setpoint != null) {
        parts += "pozostało ok. ${duration(Duration.ofSeconds((minutes * 60).toLong()))} do ${Formatters.temperature(receiver.setpoint)}"
    }
    return parts.joinToString(" · ")
}

private fun duration(d: Duration): String {
    val minutes = d.toMinutes().coerceAtLeast(1)
    return if (minutes < 60) "$minutes min" else "${minutes / 60} h ${minutes % 60} min"
}

/** A receiver as a full card: name, chamber temperature and state badge,
 * what the state means right now, the 24 h chart and stats. Receivers are
 * already a filtered view (Urządzenia → Odbiorniki), so every card stays
 * open; tapping the chart opens it full screen. */
@Composable
private fun ReceiverCardView(card: ReceiverCard, onOpenChart: () -> Unit) {
    val receiver = card.receiver
    val look = stateLook(receiver.state)
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, FrigoAccent.copy(alpha = 0.35f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(start = 16.dp, end = 12.dp, top = 12.dp, bottom = 12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    receiver.name.uppercase(),
                    color = FrigoText,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                Spacer(Modifier.width(12.dp))
                Text(
                    Formatters.temperature(receiver.chamber_temperature),
                    color = FrigoAccent,
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    style = TabularNumbers,
                )
                Spacer(Modifier.weight(1f).widthIn(min = 8.dp))
                StateBadge(look)
            }
            Text(receiverStatusLine(receiver), color = FrigoTextMuted, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))
            Spacer(Modifier.height(8.dp))
            CardChart(
                card.chamber,
                FrigoAccent,
                Modifier.fillMaxWidth().height(130.dp).clickable(onClick = onOpenChart),
                secondary = card.evaporator,
                secondaryColor = EvaporatorColor,
                levels = listOfNotNull(
                    receiver.cut_in?.let { it to FrigoMax.copy(alpha = 0.8f) },
                    receiver.cut_out?.let { it to FrigoAccent.copy(alpha = 0.8f) },
                ),
            )
            Legend(hasEvaporator = card.evaporator.isNotEmpty(), receiver)
            Spacer(Modifier.height(10.dp))
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

/** Icon and label in a rounded outline, tinted by state. */
@Composable
private fun StateBadge(look: StateLook) {
    Row(
        Modifier
            .border(1.dp, look.color.copy(alpha = 0.35f), RoundedCornerShape(8.dp))
            .background(look.color.copy(alpha = 0.08f), RoundedCornerShape(8.dp))
            .padding(horizontal = 8.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(look.icon, contentDescription = null, tint = look.color, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(5.dp))
        Text(look.label.uppercase(), color = look.color, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
    }
}

@Composable
private fun Legend(hasEvaporator: Boolean, receiver: ReceiverResponse) {
    Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        LegendItem("Komora", FrigoAccent)
        if (hasEvaporator) LegendItem("Parownik", EvaporatorColor)
        receiver.cut_in?.let { LegendItem("Załącz. ${Formatters.temperature(it)}", FrigoMax) }
        receiver.cut_out?.let { LegendItem("Wyłącz. ${Formatters.temperature(it)}", FrigoAccent) }
    }
}

@Composable
private fun LegendItem(label: String, color: Color) {
    Text(label, color = color, fontSize = 11.sp, maxLines = 1)
}
