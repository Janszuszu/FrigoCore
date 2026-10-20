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
            uiState.isLoading && uiState.receivers.isEmpty() -> LoadingState()
            uiState.error != null && uiState.receivers.isEmpty() -> MessageState(uiState.error!!, onRetry = viewModel::refresh)
            uiState.day == null -> MessageState("Brak raportów. Pierwszy raport powstanie po północy, z całego minionego dnia.")
            uiState.receivers.isEmpty() -> MessageState("Brak raportu z tego dnia.")
            else -> LazyColumn(
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(uiState.receivers, key = { it.receiver_id }) { ReceiverReportCard(it) }
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

@Composable
private fun ReceiverReportCard(report: ReceiverDayReportResponse) {
    Card(
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(1.dp, FrigoAccent.copy(alpha = 0.35f)),
        colors = CardDefaults.cardColors(containerColor = FrigoSurface, contentColor = FrigoText),
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    report.name.uppercase(),
                    color = FrigoText,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                // Hours without readings make every total smaller — say so.
                if (report.covered_seconds < DAY_SECONDS * 95 / 100) {
                    Text("dane: ${duration(report.covered_seconds)}", color = FrigoTextMuted, fontSize = 13.sp)
                }
            }
            if (report.covered_seconds == 0L) {
                Text("Brak odczytów tego dnia", color = FrigoTextMuted, fontSize = 15.sp, modifier = Modifier.padding(top = 8.dp))
                return@Column
            }
            Spacer(Modifier.height(10.dp))
            Row(Modifier.height(IntrinsicSize.Min)) {
                Phase("PRACA", report.cooling_seconds, report.cooling_count, FrigoAccent, Modifier.weight(1f))
                StatDivider()
                Phase("POSTÓJ", report.idle_seconds, report.idle_count, IdleBlue, Modifier.weight(1f))
                StatDivider()
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("UDZIAŁ PRACY", color = FrigoTextMuted, fontSize = 12.sp, letterSpacing = 0.5.sp, maxLines = 1)
                    Text(
                        report.duty_percent?.let { "${Math.round(it)} %" } ?: "—",
                        color = FrigoText,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold,
                        style = TabularNumbers,
                    )
                }
            }
            HorizontalDivider(Modifier.padding(vertical = 10.dp), color = FrigoAccent.copy(alpha = 0.2f))
            Row(Modifier.height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
                Stat("MIN", report.min_temp, "°C", Modifier.weight(1f))
                StatDivider()
                Stat("ŚREDNIA", report.avg_temp, "°C", Modifier.weight(1f))
                StatDivider()
                Stat("MAX", report.max_temp, "°C", Modifier.weight(1f))
            }
            HorizontalDivider(Modifier.padding(vertical = 10.dp), color = FrigoAccent.copy(alpha = 0.2f))
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

/** Pale ice blue for idle, as on the receiver page. */
private val IdleBlue = Color(0xFF9ADCF7)

@Composable
private fun Phase(label: String, seconds: Long, count: Int, color: Color, modifier: Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, color = FrigoTextMuted, fontSize = 12.sp, letterSpacing = 0.5.sp, maxLines = 1)
        Text(duration(seconds), color = color, fontSize = 19.sp, fontWeight = FontWeight.Bold, maxLines = 1, style = TabularNumbers)
        Text(cycles(count), color = FrigoTextMuted, fontSize = 12.sp, maxLines = 1)
        Text("śr. ${average(seconds, count)}", color = FrigoTextMuted, fontSize = 12.sp, maxLines = 1, style = TabularNumbers)
    }
}

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
