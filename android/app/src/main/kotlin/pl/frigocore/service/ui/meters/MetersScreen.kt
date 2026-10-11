package pl.frigocore.service.ui.meters

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.ElectricMeter
import androidx.compose.material.icons.outlined.Functions
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.MessageState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.overview.StatDivider
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import pl.frigocore.service.ui.theme.TabularNumbers
import java.time.LocalDate
import java.util.Locale

/** Urządzenia → Liczniki. A single meter opens straight away; several are
 * offered first as full-width tiles, with all of them added up on top. A
 * meter shows its live readings, the use today / this week / this month and
 * a bar per day for the week or the month. */
@Composable
fun MetersScreen(viewModel: MetersViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    PollWhileVisible { viewModel.refresh() }
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }

    val cards = uiState.cards
    val single = cards.singleOrNull()
    // A selection from another object (or a removed meter) falls back to the tiles.
    val selected = single ?: cards.firstOrNull { it.id == selectedId }
    BackHandler(enabled = single == null && selected != null) { selectedId = null }

    when {
        uiState.isLoading && cards.isEmpty() -> LoadingState()
        uiState.error != null && cards.isEmpty() -> MessageState(uiState.error.orEmpty(), viewModel::refresh)
        cards.isEmpty() -> MessageState("Ten obiekt nie ma jeszcze liczników.")
        selected == null -> LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
            contentPadding = PaddingValues(top = 10.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(cards, key = { it.id }) { card -> MeterTile(card) { selectedId = card.id } }
        }
        else -> LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
            contentPadding = PaddingValues(top = 10.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item(key = "head") { MeterHead(selected, onBack = if (single == null) ({ selectedId = null }) else null) }
            item(key = "periods") { Periods(selected) }
            item(key = "chart") { UsageChartCard(selected) }
        }
    }
}

private val shape = RoundedCornerShape(10.dp)

@Composable
private fun FrigoCard(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable () -> Unit) {
    val border = BorderStroke(1.dp, FrigoAccent.copy(alpha = 0.35f))
    val colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText)
    if (onClick != null) Card(onClick = onClick, shape = shape, border = border, colors = colors, modifier = modifier.fillMaxWidth()) { content() }
    else Card(shape = shape, border = border, colors = colors, modifier = modifier.fillMaxWidth()) { content() }
}

@Composable
private fun MeterTile(card: MeterCard, onClick: () -> Unit) {
    FrigoCard(onClick = onClick) {
        Column(
            Modifier.fillMaxWidth().heightIn(min = 120.dp).padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Icon(
                if (card.isTotal) Icons.Outlined.Functions else Icons.Outlined.ElectricMeter,
                contentDescription = null,
                tint = FrigoAccent,
                modifier = Modifier.size(32.dp),
            )
            Spacer(Modifier.height(8.dp))
            Text(card.name.uppercase(), fontWeight = FontWeight.Bold, fontSize = 15.sp, textAlign = TextAlign.Center, maxLines = 2)
            Text(
                "Dziś ${kwh(card.consumption.today_kwh)} · miesiąc ${kwh(card.consumption.month_kwh)}",
                color = FrigoTextMuted,
                fontSize = 12.sp,
                textAlign = TextAlign.Center,
                style = TabularNumbers,
            )
        }
    }
}

/** Name, and the live power / current / voltage the meter reports. */
@Composable
private fun MeterHead(card: MeterCard, onBack: (() -> Unit)?) {
    FrigoCard {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
            Box(Modifier.fillMaxWidth().heightIn(min = 40.dp), contentAlignment = Alignment.Center) {
                if (onBack != null) {
                    IconButton(onClick = onBack, modifier = Modifier.align(Alignment.CenterStart)) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Wszystkie liczniki", tint = FrigoAccent)
                    }
                }
                Text(
                    card.name.uppercase(),
                    color = FrigoAccent,
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp,
                    textAlign = TextAlign.Center,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(horizontal = 44.dp),
                )
            }
            val live = listOfNotNull(
                card.powerW?.let { (if (card.isTotal) "MOC ŁĄCZNA" else "MOC") to Formatters.reading(it, "W") },
                card.currentA?.let { "PRĄD" to Formatters.reading(it, "A") },
                card.voltageV?.let { "NAPIĘCIE" to Formatters.reading(it, "V") },
            )
            if (live.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
                    live.forEachIndexed { i, (label, value) ->
                        if (i > 0) StatDivider()
                        Figure(label, value, Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

@Composable
private fun Figure(label: String, value: String, modifier: Modifier = Modifier, big: Boolean = false) {
    Column(modifier.padding(vertical = 2.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, color = FrigoTextMuted, fontSize = 11.sp, letterSpacing = 0.5.sp, maxLines = 1)
        Text(
            value,
            color = FrigoText,
            fontSize = if (big) 22.sp else 18.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            style = TabularNumbers,
        )
    }
}

/** Today, this week, this month and the counter itself. */
@Composable
private fun Periods(card: MeterCard) {
    FrigoCard {
        Column(Modifier.padding(horizontal = 8.dp, vertical = 12.dp)) {
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
                Figure("DZIŚ", kwh(card.consumption.today_kwh), Modifier.weight(1f), big = true)
                StatDivider()
                Figure("TEN TYDZIEŃ", kwh(card.consumption.week_kwh), Modifier.weight(1f), big = true)
            }
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
                Figure("TEN MIESIĄC", kwh(card.consumption.month_kwh), Modifier.weight(1f), big = true)
                StatDivider()
                Figure(if (card.isTotal) "LICZNIKI RAZEM" else "STAN LICZNIKA", kwh(card.totalKwh), Modifier.weight(1f), big = true)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
/** Bars per day — this week (Monday to Sunday) or this month. Tapping a bar
 * names its day and its consumption above the chart. */
@Composable
private fun UsageChartCard(card: MeterCard) {
    var month by rememberSaveable { mutableStateOf(false) }
    val today = LocalDate.now(MeterZone)
    val bars = remember(card.consumption, month, today) {
        if (month) monthBars(card.consumption, today) else weekBars(card.consumption, today)
    }
    var picked by remember(bars) { mutableStateOf<DayBar?>(null) }

    FrigoCard {
        Column(Modifier.padding(12.dp)) {
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                listOf("Tydzień", "Miesiąc").forEachIndexed { i, label ->
                    SegmentedButton(
                        selected = month == (i == 1),
                        onClick = { month = i == 1 },
                        shape = SegmentedButtonDefaults.itemShape(i, 2),
                        colors = SegmentedButtonDefaults.colors(
                            activeContainerColor = FrigoAccent.copy(alpha = 0.18f),
                            activeContentColor = FrigoAccent,
                            activeBorderColor = FrigoAccent,
                            inactiveContainerColor = FrigoSurface,
                            inactiveContentColor = FrigoText,
                            inactiveBorderColor = FrigoOutline,
                        ),
                    ) { Text(label) }
                }
            }
            Spacer(Modifier.height(10.dp))
            val shown = picked
            Text(
                if (shown != null) "${dayTitle(shown.day)}: ${kwh(shown.kwh)}"
                else "Suma: ${kwh(bars.mapNotNull { it.kwh }.takeIf { it.isNotEmpty() }?.sum())}",
                color = FrigoAccent,
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp,
                modifier = Modifier.fillMaxWidth(),
                textAlign = TextAlign.Center,
                style = TabularNumbers,
            )
            Spacer(Modifier.height(6.dp))
            DayBars(
                bars,
                today = today,
                labelEvery = if (month) 5 else 1,
                showValues = !month,
                picked = picked,
                onPick = { picked = if (picked == it) null else it },
                modifier = Modifier.fillMaxWidth().height(if (month) 180.dp else 200.dp),
            )
        }
    }
}

@Composable
private fun DayBars(
    bars: List<DayBar>,
    today: LocalDate,
    labelEvery: Int,
    showValues: Boolean,
    picked: DayBar?,
    onPick: (DayBar) -> Unit,
    modifier: Modifier = Modifier,
) {
    val textMeasurer = rememberTextMeasurer()
    val labelStyle = TextStyle(fontSize = 11.sp, color = FrigoTextMuted)
    val valueStyle = TextStyle(fontSize = 11.sp, color = FrigoText, fontWeight = FontWeight.Bold)
    val max = bars.mapNotNull { it.kwh }.maxOrNull()?.takeIf { it > 0 } ?: 1.0
    Canvas(
        modifier.pointerInput(bars) {
            detectTapGestures { offset ->
                val slot = size.width / bars.size.toFloat()
                bars.getOrNull((offset.x / slot).toInt())?.let(onPick)
            }
        },
    ) {
        val slot = size.width / bars.size
        val bottomPad = 20.dp.toPx()
        val topPad = if (showValues) 18.dp.toPx() else 4.dp.toPx()
        val chartH = size.height - bottomPad - topPad
        val barW = slot * 0.62f
        drawLine(FrigoOutline, Offset(0f, topPad + chartH), Offset(size.width, topPad + chartH), 1f)
        bars.forEachIndexed { i, bar ->
            val cx = slot * i + slot / 2
            val future = bar.day.isAfter(today)
            val highlight = bar == picked || (picked == null && bar.day == today)
            val kwh = bar.kwh
            if (kwh != null && !future) {
                val h = (kwh / max).toFloat() * chartH
                drawRoundRect(
                    if (highlight) FrigoAccent else FrigoAccent.copy(alpha = 0.55f),
                    topLeft = Offset(cx - barW / 2, topPad + chartH - h),
                    size = Size(barW, h.coerceAtLeast(1.dp.toPx())),
                    cornerRadius = CornerRadius(3.dp.toPx()),
                )
                if (showValues) {
                    val value = textMeasurer.measure(String.format(Locale.forLanguageTag("pl"), "%.1f", kwh), valueStyle)
                    drawText(value, topLeft = Offset(cx - value.size.width / 2, topPad + chartH - h - value.size.height - 2.dp.toPx()))
                }
            }
            val n = bar.day.dayOfMonth
            if (labelEvery == 1 || n == 1 || n % labelEvery == 0) {
                val text = if (labelEvery == 1) weekdayLabel(bar.day) else "$n"
                val label = textMeasurer.measure(text, if (bar.day == today) labelStyle.copy(color = FrigoAccent) else labelStyle)
                drawText(label, topLeft = Offset(cx - label.size.width / 2, size.height - label.size.height))
            }
        }
    }
}
