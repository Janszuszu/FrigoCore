package pl.frigocore.service.ui.home

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import pl.frigocore.service.ui.common.quietClickable
import pl.frigocore.service.ui.theme.Barlow
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoTextMuted

private val DeviceGroups = listOf("ODBIORNIKI", "AGREGATY", "LICZNIKI")

/** Urządzenia: receivers, aggregates and meters side by side — a swipe
 * left or right changes the group (the receivers' own pages swipe first,
 * the group changes past their last one). The names on top show where you
 * are and jump there on a tap. [page] / [onPage] keep the group across
 * tab switches. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun DevicesPager(
    page: Int,
    onPage: (Int) -> Unit,
    receivers: @Composable () -> Unit,
    aggregates: @Composable () -> Unit,
    meters: @Composable () -> Unit,
) {
    val pagerState = rememberPagerState(initialPage = page.coerceIn(0, DeviceGroups.lastIndex)) { DeviceGroups.size }
    val scope = rememberCoroutineScope()
    LaunchedEffect(pagerState) { snapshotFlow { pagerState.currentPage }.collect(onPage) }
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(top = 6.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            DeviceGroups.forEachIndexed { i, name ->
                val current = i == pagerState.currentPage
                Column(
                    Modifier
                        .quietClickable { scope.launch { pagerState.animateScrollToPage(i) } }
                        .padding(horizontal = 14.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        name,
                        color = if (current) FrigoAccent else FrigoTextMuted,
                        style = TextStyle(
                            fontFamily = Barlow,
                            fontWeight = if (current) FontWeight.SemiBold else FontWeight.Medium,
                            fontSize = 15.sp,
                            letterSpacing = 1.sp,
                        ),
                    )
                    Box(
                        Modifier
                            .padding(top = 3.dp)
                            .width(24.dp)
                            .height(2.dp)
                            .background(if (current) FrigoAccent else FrigoAccent.copy(alpha = 0f)),
                    )
                }
            }
        }
        HorizontalPager(state = pagerState, modifier = Modifier.weight(1f).fillMaxWidth()) { i ->
            when (i) {
                0 -> receivers()
                1 -> aggregates()
                else -> meters()
            }
        }
    }
}
