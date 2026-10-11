package pl.frigocore.service.ui.aggregates

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.Hvac
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.data.model.AggregateResponse
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.MessageState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.overview.SensorCardView
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Urządzenia → Agregaty. A single aggregate opens straight away; several
 * are offered first as full-width tiles, one under another. An aggregate shows its nameplate on top and
 * its sensors below as slim rows that unfold into the 24 h chart. */
@Composable
fun AggregatesScreen(
    onSensorClick: (SensorResponse) -> Unit,
    viewModel: AggregatesViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible { viewModel.refresh() }
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var expanded by rememberSaveable { mutableStateOf(emptyList<String>()) }

    val aggregates = uiState.aggregates
    val single = aggregates.singleOrNull()
    // A selection from another object (or a removed aggregate) falls back to the tiles.
    val selected = single ?: aggregates.firstOrNull { it.aggregate.id == selectedId }
    BackHandler(enabled = single == null && selected != null) { selectedId = null }

    when {
        uiState.isLoading && aggregates.isEmpty() -> LoadingState()
        uiState.error != null && aggregates.isEmpty() -> MessageState(uiState.error.orEmpty(), viewModel::refresh)
        aggregates.isEmpty() -> MessageState("Ten obiekt nie ma jeszcze agregatów.")
        selected == null -> LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
            contentPadding = PaddingValues(top = 10.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(aggregates, key = { it.aggregate.id }) { card ->
                AggregateTile(card) { selectedId = card.aggregate.id }
            }
        }
        else -> LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
            contentPadding = PaddingValues(top = 10.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            item(key = "nameplate") {
                Nameplate(selected.aggregate, onBack = if (single == null) ({ selectedId = null }) else null)
                Spacer(Modifier.height(4.dp))
            }
            if (selected.sensors.isEmpty()) {
                item(key = "empty") {
                    Text(
                        "Brak czujników przypisanych do tego agregatu.",
                        color = FrigoTextMuted,
                        modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
                        textAlign = TextAlign.Center,
                    )
                }
            }
            items(selected.sensors, key = { it.sensor.id }) { card ->
                val id = card.sensor.id
                SensorCardView(
                    card,
                    expanded = id in expanded,
                    onToggle = { expanded = if (id in expanded) expanded - id else expanded + id },
                    onOpenChart = { onSensorClick(card.sensor) },
                )
            }
        }
    }
}

@Composable
private fun AggregateTile(card: AggregateCard, onClick: () -> Unit) {
    val edge = if (card.alarm) FrigoCritical else FrigoAccent
    Card(
        onClick = onClick,
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, edge.copy(alpha = if (card.alarm) 0.8f else 0.35f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            Modifier.fillMaxWidth().heightIn(min = 120.dp).padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Icon(
                if (card.alarm) Icons.Outlined.WarningAmber else Icons.Outlined.Hvac,
                contentDescription = if (card.alarm) "Alarm" else null,
                tint = edge,
                modifier = Modifier.size(32.dp),
            )
            Spacer(Modifier.height(8.dp))
            Text(
                card.aggregate.name.uppercase(),
                fontWeight = FontWeight.Bold,
                fontSize = 15.sp,
                textAlign = TextAlign.Center,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            listOfNotNull(card.aggregate.compressor_model, card.aggregate.refrigerant)
                .joinToString(" · ")
                .takeIf { it.isNotEmpty() }
                ?.let {
                    Text(it, color = FrigoTextMuted, fontSize = 12.sp, textAlign = TextAlign.Center, maxLines = 2)
                }
        }
    }
}

/** Name on top, then compressor and its cooling capacity, refrigerant and
 * its charge, and the installation date. [onBack] returns to the tiles when there are several. */
@Composable
private fun Nameplate(aggregate: AggregateResponse, onBack: (() -> Unit)?) {
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, FrigoAccent.copy(alpha = 0.35f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
            Box(Modifier.fillMaxWidth().heightIn(min = 40.dp), contentAlignment = Alignment.Center) {
                if (onBack != null) {
                    IconButton(onClick = onBack, modifier = Modifier.align(Alignment.CenterStart)) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Wszystkie agregaty", tint = FrigoAccent)
                    }
                }
                Text(
                    aggregate.name.uppercase(),
                    color = FrigoAccent,
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp,
                    textAlign = TextAlign.Center,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(horizontal = 44.dp),
                )
            }
            Spacer(Modifier.height(6.dp))
            Row(Modifier.fillMaxWidth()) {
                Fact("Model sprężarki", aggregate.compressor_model, Modifier.weight(1f))
                Fact("Moc chłodnicza", aggregate.cooling_capacity_kw?.let { formatAmount(it, "kW") }, Modifier.weight(1f))
            }
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth()) {
                Fact("Czynnik", aggregate.refrigerant, Modifier.weight(1f))
                Fact("Ilość czynnika", aggregate.refrigerant_charge_kg?.let { formatAmount(it, "kg") }, Modifier.weight(1f))
            }
            Spacer(Modifier.height(8.dp))
            Fact("Data instalacji", aggregate.installed_on?.let(::formatDate))
        }
    }
}

@Composable
private fun Fact(label: String, value: String?, modifier: Modifier = Modifier) {
    Column(modifier.padding(end = 8.dp)) {
        Text(label.uppercase(), color = FrigoTextMuted, fontSize = 11.sp, maxLines = 1)
        Text(
            value ?: "—",
            color = FrigoText,
            fontSize = 15.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

private val dateFormat = DateTimeFormatter.ofPattern("dd.MM.yyyy")

/** "2021-06-15" → "15.06.2021"; anything unparsable is shown as sent. */
internal fun formatDate(iso: String): String =
    runCatching { LocalDate.parse(iso).format(dateFormat) }.getOrDefault(iso)

/** (4.2, "kg") → "4,2 kg", (6.0, "kW") → "6 kW". */
internal fun formatAmount(value: Double, unit: String): String {
    val text = "%.2f".format(Locale.ROOT, value).trimEnd('0').trimEnd('.')
    return "${text.replace('.', ',')} $unit"
}
