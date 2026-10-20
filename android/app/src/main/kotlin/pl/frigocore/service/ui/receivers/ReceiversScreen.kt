package pl.frigocore.service.ui.receivers

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.HelpOutline
import androidx.compose.material.icons.outlined.AcUnit
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material.icons.outlined.WbSunny
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import pl.frigocore.service.data.model.ReceiverState
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.LoadingState
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.common.quietClickable
import pl.frigocore.service.ui.sensor.ChartPoint
import pl.frigocore.service.ui.theme.Barlow
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoMax
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import java.time.Instant
import java.time.temporal.ChronoUnit

/** Receivers on one page. */
private const val PER_PAGE = 3

/** Urządzenia → Odbiorniki: three receivers to a page, more a swipe away
 * with dots for where you are. Each card is the chamber — name, state,
 * temperature, its 24 h chart and MIN / ŚREDNIA / MAX — plus the
 * evaporator's reading. Tapping the chart opens the chamber full screen,
 * tapping PAROWNIK the evaporator. */
@OptIn(ExperimentalFoundationApi::class)
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
        // Another object starts again on its first page.
        else -> key(uiState.objectId) {
            val pages = uiState.cards.chunked(PER_PAGE)
            val pagerState = rememberPagerState { pages.size }
            Column(Modifier.fillMaxSize()) {
                HorizontalPager(
                    state = pagerState,
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    pageSpacing = 12.dp,
                ) { page ->
                    val group = pages.getOrNull(page) ?: return@HorizontalPager
                    Column(
                        Modifier.fillMaxSize().padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        group.forEach { card ->
                            ReceiverCardView(
                                card,
                                onOpenChart = { sensorId, name -> onOpenChart(card.receiver.object_id, sensorId, name) },
                                modifier = Modifier.weight(1f).fillMaxWidth(),
                            )
                        }
                        // A short last page keeps the cards the size they are on the others.
                        if (pages.size > 1 && group.size < PER_PAGE) {
                            Spacer(Modifier.weight((PER_PAGE - group.size).toFloat()))
                        }
                    }
                }
                if (pages.size > 1) PageDots(pages.size, pagerState.currentPage)
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
    // In range, cooling or idle alike: a blue snowflake.
    ReceiverState.COOLING -> StateLook("Chłodzenie", Icons.Outlined.AcUnit, FrigoAccent)
    ReceiverState.IDLE -> StateLook("Postój", Icons.Outlined.AcUnit, FrigoAccent)
    ReceiverState.DEFROST -> StateLook("Odszranianie", Icons.Outlined.WbSunny, FrigoMax)
    else -> StateLook("Nieznany", Icons.AutoMirrored.Outlined.HelpOutline, FrigoTextMuted)
}

private val AlarmLook = StateLook("Alarm", Icons.Outlined.WarningAmber, FrigoCritical)

/** Mint green of the chart while the receiver is in range. */
private val Mint = Color(0xFF34E0A1)

/** The chart's colour: mint in range (cooling or idle), orange defrost, red
 * alarm, grey when the state is unknown. The rest of the card keeps its own. */
private fun chartColor(alarm: Boolean, state: String): Color = when {
    alarm -> FrigoCritical
    state == ReceiverState.DEFROST -> FrigoMax
    state == ReceiverState.COOLING || state == ReceiverState.IDLE -> Mint
    else -> FrigoTextMuted
}

private val NameStyle = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Medium, fontSize = 24.sp, letterSpacing = 0.5.sp)
private val TempStyle = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.SemiBold, fontSize = 38.sp, fontFeatureSettings = "tnum")
private val LabelStyle = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Normal, fontSize = 13.sp, letterSpacing = 1.sp)
private val ValueStyle = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.SemiBold, fontSize = 22.sp, fontFeatureSettings = "tnum")

/** Name in white on the left, the state icon exactly in the middle, the
 * temperature on the right; the chart; MIN / ŚREDNIA / MAX and PAROWNIK.
 * Readings, chart and border take the state colour (blue in range, orange
 * defrost, red alarm). */
@Composable
private fun ReceiverCardView(
    card: ReceiverCard,
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
        Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 10.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    receiver.name.uppercase(),
                    color = FrigoText,
                    style = NameStyle,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Icon(look.icon, contentDescription = look.label, tint = look.color, modifier = Modifier.padding(horizontal = 8.dp).size(30.dp))
                Text(
                    Formatters.temperature(receiver.chamber_temperature),
                    color = look.color,
                    style = TempStyle,
                    maxLines = 1,
                    textAlign = TextAlign.End,
                    modifier = Modifier.weight(1f),
                )
            }
            ReceiverChart(
                card.chamber,
                chartColor(card.alarm, receiver.state),
                Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(vertical = 6.dp)
                    .quietClickable { receiver.chamber_sensor_id?.let { onOpenChart(it, receiver.name) } },
            )
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), verticalAlignment = Alignment.CenterVertically) {
                StatCell("MIN", card.stats?.min, look.color, Modifier.weight(1f))
                CellDivider()
                StatCell("ŚREDNIA", card.stats?.avg, look.color, Modifier.weight(1f))
                CellDivider()
                StatCell("MAX", card.stats?.max, look.color, Modifier.weight(1f))
                val evaporatorId = receiver.evaporator_sensor_id
                if (evaporatorId != null) {
                    CellDivider()
                    StatCell(
                        "PAROWNIK",
                        receiver.evaporator_temperature,
                        look.color,
                        Modifier.weight(1f).quietClickable { onOpenChart(evaporatorId, "${receiver.name} — parownik") },
                    )
                }
            }
        }
    }
}

@Composable
private fun StatCell(label: String, value: Double?, color: Color, modifier: Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, color = FrigoTextMuted, style = LabelStyle, maxLines = 1)
        Text(Formatters.temperature(value), color = color, style = ValueStyle, maxLines = 1)
    }
}

@Composable
private fun CellDivider() {
    Box(Modifier.width(1.dp).fillMaxHeight().padding(vertical = 4.dp).background(FrigoAccent.copy(alpha = 0.35f)))
}

/** The last 24 hours as a smooth line over a fading fill, scaled to the
 * day's own range; faint dashed lines quarter the day, no labels. */
@Composable
private fun ReceiverChart(points: List<ChartPoint>, color: Color, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val dash = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 4.dp.toPx()))
        for (i in 1..3) {
            val x = size.width * i / 4f
            drawLine(FrigoOutline, Offset(x, 0f), Offset(x, size.height), 1f, pathEffect = dash)
        }
        drawLine(FrigoOutline, Offset(0f, 0f), Offset(size.width, 0f), 1f)
        drawLine(FrigoTextMuted.copy(alpha = 0.6f), Offset(0f, size.height), Offset(size.width, size.height), 1f)

        val now = Instant.now()
        val start = now.minus(24, ChronoUnit.HOURS).toEpochMilli()
        val span = (now.toEpochMilli() - start).toFloat()
        val visible = points.filter { it.time.toEpochMilli() >= start }
        if (visible.size < 2) return@Canvas
        val lo = visible.minOf { it.value }
        val hi = visible.maxOf { it.value }
        val range = (hi - lo).coerceAtLeast(1.0)
        // Headroom over the peak, and the lowest reading a little above the floor.
        val top = 4.dp.toPx()
        val bottom = size.height * 0.82f
        fun x(p: ChartPoint) = ((p.time.toEpochMilli() - start) / span).coerceIn(0f, 1f) * size.width
        fun y(p: ChartPoint) = bottom - ((p.value - lo) / range).toFloat() * (bottom - top)

        // Smooth: a quadratic curve through the midpoints between readings.
        val line = Path().apply {
            moveTo(x(visible[0]), y(visible[0]))
            for (i in 1 until visible.size) {
                val px = x(visible[i - 1])
                val py = y(visible[i - 1])
                quadraticBezierTo(px, py, (px + x(visible[i])) / 2, (py + y(visible[i])) / 2)
            }
            lineTo(x(visible.last()), y(visible.last()))
        }
        val fill = Path().apply {
            addPath(line)
            lineTo(x(visible.last()), size.height)
            lineTo(x(visible.first()), size.height)
            close()
        }
        drawPath(fill, Brush.verticalGradient(listOf(color.copy(alpha = 0.42f), color.copy(alpha = 0.02f)), top, size.height))
        drawPath(line, color, style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}
