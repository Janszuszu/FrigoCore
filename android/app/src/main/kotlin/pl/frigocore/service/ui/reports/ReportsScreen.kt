package pl.frigocore.service.ui.reports

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Hvac
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.data.model.AggregateDayReportResponse
import pl.frigocore.service.data.model.ReceiverDayReportResponse
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.MessageState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.overview.Stat
import pl.frigocore.service.ui.overview.StatDivider
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoMax
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import pl.frigocore.service.ui.theme.TabularNumbers
import java.time.ZoneId

/** The backend cuts report days at Polish midnight; times read the same way. */
private val ReportZone: ZoneId = ZoneId.of("Europe/Warsaw")

/** Raport: one card per receiver for the chosen day — cooling and idle
 * time with their cycle counts and average lengths, the share of the day
 * the compressor ran, min / average / max, and each defrost with its start,
 * length, peak and recovery. The days are paged with the arrows. */
@Composable
fun ReportsScreen(viewModel: ReportsViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    // A report is written once a night; a slow poll picks up the new day.
    PollWhileVisible(intervalMillis = 10 * 60_000) { viewModel.refresh() }

    Column(Modifier.fillMaxSize()) {
        DayPicker(uiState, viewModel::showDay)
        when {
            uiState.isLoading && uiState.receivers.isEmpty() && uiState.aggregates.isEmpty() -> LoadingState()
            uiState.error != null && uiState.receivers.isEmpty() && uiState.aggregates.isEmpty() ->
                MessageState(uiState.error!!, onRetry = viewModel::refresh)
            uiState.day == null -> MessageState("Brak raportów. Pierwszy raport powstanie po północy, z całego minionego dnia.")
            uiState.receivers.isEmpty() && uiState.aggregates.isEmpty() -> MessageState("Brak raportu z tego dnia.")
            else -> LazyColumn(
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(uiState.receivers, key = { it.receiver_id }) { ReceiverReportCard(it) }
                items(uiState.aggregates, key = { it.aggregate_id }) { AggregateReportCard(it) }
            }
        }
    }
}

@Composable
private fun DayPicker(uiState: ReportsUiState, onDay: (java.time.LocalDate) -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val older = uiState.older
        val newer = uiState.newer
        IconButton(onClick = { older?.let(onDay) }, enabled = older != null) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, contentDescription = "Poprzedni dzień", tint = if (older != null) FrigoAccent else FrigoTextMuted.copy(alpha = 0.3f))
        }
        Text(
            uiState.day?.let(::dayHeading) ?: "Raport dzienny",
            color = FrigoText,
            fontSize = 17.sp,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center,
            maxLines = 1,
            style = TabularNumbers,
            modifier = Modifier.weight(1f),
        )
        IconButton(onClick = { newer?.let(onDay) }, enabled = newer != null) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = "Następny dzień", tint = if (newer != null) FrigoAccent else FrigoTextMuted.copy(alpha = 0.3f))
        }
    }
}

/** "1 cykl", "3 cykle", "12 cykli". */
internal fun cycles(n: Int): String = when {
    n == 1 -> "1 cykl"
    n % 10 in 2..4 && n % 100 !in 12..14 -> "$n cykle"
    else -> "$n cykli"
}

private const val DAY_SECONDS = 24 * 3600L

/** Card heading: the name, and under it how much of the day the readings
 * cover when they don't cover (nearly) all of it — every total is smaller then. */
@Composable
private fun CardHead(name: String, coveredSeconds: Long, icon: (@Composable () -> Unit)? = null) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        if (icon != null) {
            icon()
            Spacer(Modifier.width(8.dp))
        }
        Column {
            Text(
                name.uppercase(),
                color = FrigoText,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            if (coveredSeconds in 1 until DAY_SECONDS * 95 / 100) {
                Text("dane z ${duration(coveredSeconds)} doby", color = FrigoTextMuted, fontSize = 13.sp)
            }
        }
    }
}

/** One figure per line: the label on the left, the value on the right. */
@Composable
private fun ReportRow(label: String, value: String, color: Color = FrigoText, strong: Boolean = false) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = if (strong) FrigoText else FrigoTextMuted, fontSize = 15.sp, modifier = Modifier.weight(1f))
        Text(
            value,
            color = color,
            fontSize = if (strong) 19.sp else 16.sp,
            fontWeight = if (strong) FontWeight.Bold else FontWeight.SemiBold,
            maxLines = 1,
            style = TabularNumbers,
        )
    }
}

@Composable
private fun Section(color: Color) {
    HorizontalDivider(Modifier.padding(vertical = 6.dp), color = color.copy(alpha = 0.2f))
}

private fun percent(value: Double?): String = value?.let { "${Math.round(it)} %" } ?: "—"

@Composable
private fun ReceiverReportCard(report: ReceiverDayReportResponse) {
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, FrigoAccent.copy(alpha = 0.35f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp)) {
            CardHead(report.name, report.covered_seconds)
            if (report.covered_seconds == 0L) {
                Text("Brak odczytów tego dnia", color = FrigoTextMuted, fontSize = 15.sp, modifier = Modifier.padding(top = 8.dp))
                return@Column
            }
            Section(FrigoAccent)
            ReportRow("Praca", duration(report.cooling_seconds), FrigoAccent, strong = true)
            ReportRow("Cykle pracy", "${report.cooling_count}")
            ReportRow("Średni czas pracy", average(report.cooling_seconds, report.cooling_count))
            ReportRow("Postój", duration(report.idle_seconds), IdleBlue, strong = true)
            ReportRow("Średni postój", average(report.idle_seconds, report.idle_count))
            ReportRow("Udział pracy", percent(report.duty_percent), strong = true)
            Section(FrigoAccent)
            ReportRow("Temperatura min.", Formatters.temperature(report.min_temp), FrigoAccent)
            ReportRow("Temperatura średnia", Formatters.temperature(report.avg_temp), FrigoAccent)
            ReportRow("Temperatura maks.", Formatters.temperature(report.max_temp), FrigoAccent)
            Section(FrigoAccent)
            Defrosts(report)
            report.off_periods.forEach { off ->
                val from = Formatters.parseInstant(off.start)?.let { Formatters.time(it, ReportZone) } ?: "—"
                val to = Formatters.parseInstant(off.end)?.let { Formatters.time(it, ReportZone) } ?: "—"
                Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.WarningAmber, contentDescription = null, tint = FrigoCritical, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "Wyłączenie lub awaria $from–$to, do ${Formatters.temperature(off.peak)}",
                        color = FrigoCritical,
                        fontSize = 14.sp,
                    )
                }
            }
        }
    }
}

/** An aggregate's day from its power draw, one figure per line: running
 * and resting time with the starts and run lengths, the duty share, and —
 * from a power sensor — the energy used and the average power while running. */
@Composable
private fun AggregateReportCard(report: AggregateDayReportResponse) {
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, FrigoMax.copy(alpha = 0.4f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp)) {
            CardHead("Agregat ${report.name}", report.covered_seconds) {
                Icon(Icons.Outlined.Hvac, contentDescription = null, tint = FrigoMax, modifier = Modifier.size(24.dp))
            }
            if (report.covered_seconds == 0L) {
                Text("Brak odczytów tego dnia", color = FrigoTextMuted, fontSize = 15.sp, modifier = Modifier.padding(top = 8.dp))
                return@Column
            }
            val power = report.source == "power"
            Section(FrigoMax)
            ReportRow("Praca", duration(report.running_seconds), FrigoMax, strong = true)
            ReportRow("Załączenia", "${report.starts}")
            ReportRow("Średni czas pracy", report.avg_run_seconds?.let { average(it, 1) } ?: "—")
            ReportRow("Najdłuższa praca", report.max_run_seconds?.let { average(it, 1) } ?: "—")
            ReportRow("Postój", duration(report.idle_seconds), IdleBlue, strong = true)
            ReportRow("Średni postój", report.avg_idle_seconds?.let { average(it, 1) } ?: "—")
            ReportRow("Udział pracy", percent(report.duty_percent), strong = true)
            Section(FrigoMax)
            ReportRow("Energia", report.energy_kwh?.let { Formatters.reading(it, "kWh") } ?: "—", strong = true)
            ReportRow(
                if (power) "Średnia moc w pracy" else "Średni prąd w pracy",
                Formatters.reading(report.avg_running_value, if (power) "W" else "A"),
            )
        }
    }
}

/** "1 załączenie", "3 załączenia", "12 załączeń". */
internal fun starts(n: Int): String = when {
    n == 1 -> "1 załączenie"
    n % 10 in 2..4 && n % 100 !in 12..14 -> "$n załączenia"
    else -> "$n załączeń"
}

/** Pale ice blue for idle, as on the receiver page. */
private val IdleBlue = Color(0xFF9ADCF7)

/** Each defrost on its own line: start, length, peak and recovery. */
@Composable
private fun Defrosts(report: ReceiverDayReportResponse) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Outlined.WbSunny, contentDescription = null, tint = FrigoMax, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(8.dp))
        Text("ODSZRANIANIA", color = FrigoTextMuted, fontSize = 12.sp, letterSpacing = 0.5.sp, modifier = Modifier.weight(1f))
        Text("${report.defrost_count}", color = FrigoMax, fontSize = 18.sp, fontWeight = FontWeight.Bold, style = TabularNumbers)
    }
    if (report.defrosts.isEmpty()) {
        Text("Brak odszraniania", color = FrigoTextMuted, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
        return
    }
    Row(Modifier.fillMaxWidth().padding(top = 8.dp)) {
        listOf("GODZ.", "CZAS", "SZCZYT", "POWRÓT").forEach {
            Text(it, color = FrigoTextMuted, fontSize = 11.sp, modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
        }
    }
    report.defrosts.forEach { d ->
        val start = Formatters.parseInstant(d.start)
        val end = Formatters.parseInstant(d.end)
        val length = if (start != null && end != null) end.epochSecond - start.epochSecond else null
        Row(Modifier.fillMaxWidth().padding(top = 4.dp)) {
            listOf(
                start?.let { Formatters.time(it, ReportZone) } ?: "—",
                duration(length),
                Formatters.temperature(d.peak),
                duration(d.recovery_seconds),
            ).forEachIndexed { i, text ->
                Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                    Text(
                        text,
                        color = if (i == 0) FrigoMax else FrigoText,
                        fontSize = 15.sp,
                        fontWeight = if (i == 0) FontWeight.SemiBold else FontWeight.Normal,
                        maxLines = 1,
                        style = TabularNumbers,
                    )
                }
            }
        }
    }
}
