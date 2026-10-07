package pl.frigocore.service.ui.home

import android.net.Uri
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.outlined.Apartment
import androidx.compose.material.icons.outlined.NotificationsNone
import androidx.compose.material.icons.outlined.ViewInAr
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import pl.frigocore.service.data.local.SelectedObjectStore
import pl.frigocore.service.data.model.UserRole
import pl.frigocore.service.data.repository.AlarmRepository
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.AuthRepository
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.common.PollWhileVisible
import pl.frigocore.service.ui.dashboard.DashboardScreen
import pl.frigocore.service.ui.objects.ObjectsScreen
import pl.frigocore.service.ui.overview.isOpen
import pl.frigocore.service.ui.overview.OverviewScreen
import pl.frigocore.service.ui.sensor.SensorScreen
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoBackground
import pl.frigocore.service.ui.theme.FrigoCritical
import pl.frigocore.service.ui.theme.FrigoOk
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import java.time.Duration
import java.time.Instant
import javax.inject.Inject

data class HeaderState(val openAlarms: Int = 0, val lastSuccessAt: Instant? = null) {
    fun isLive(now: Instant = Instant.now()): Boolean =
        lastSuccessAt != null && Duration.between(lastSuccessAt, now).seconds <= 75
}

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val alarmRepository: AlarmRepository,
    private val selectedObjectStore: SelectedObjectStore,
) : ViewModel() {
    /** Owners (`user` role) only watch their objects; everyone else is
     * service staff who can act on alarms. */
    val isTechnician: Boolean = authRepository.currentUser?.role != UserRole.USER
    val displayName: String = authRepository.currentUser?.let { it.full_name.ifBlank { it.username } }.orEmpty()

    private val _header = MutableStateFlow(HeaderState())
    val header: StateFlow<HeaderState> = _header.asStateFlow()

    fun refreshHeader() {
        viewModelScope.launch {
            when (val result = alarmRepository.listAlarms()) {
                is ApiResult.Success -> _header.value = HeaderState(result.data.count(::isOpen), Instant.now())
                is ApiResult.Error -> Unit // LIVE goes stale on its own once polls keep failing
            }
        }
    }

    fun selectObject(objectId: String) = selectedObjectStore.select(objectId)

    fun logout(onDone: () -> Unit) {
        viewModelScope.launch {
            authRepository.logout()
            onDone()
        }
    }
}

private object HomeRoutes {
    const val OVERVIEW = "overview"
    const val OBJECTS = "objects"
    const val ALARMS = "alarms"
    const val SENSOR = "sensor/{objectId}/{sensorId}?name={name}"

    fun sensorRoute(objectId: String, sensorId: String, name: String) =
        "sensor/$objectId/$sensorId?name=${Uri.encode(name)}"
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onAlarmClick: (String) -> Unit,
    onLoggedOut: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val navController: NavHostController = rememberNavController()
    val backStack by navController.currentBackStackEntryAsState()
    val route = backStack?.destination?.route
    // The chart is full-screen: no header, no bottom bar.
    val chrome = route != HomeRoutes.SENSOR
    val header by viewModel.header.collectAsState()
    PollWhileVisible { viewModel.refreshHeader() }
    var menuOpen by remember { mutableStateOf(false) }

    Scaffold(
        containerColor = FrigoBackground,
        topBar = {
            if (chrome) {
                FrigoHeader(header = header, onAlarmsClick = { navController.switchTab(HomeRoutes.ALARMS) })
            }
        },
        bottomBar = {
            if (chrome) {
                Column {
                    HorizontalDivider(color = FrigoOutline)
                    NavigationBar(containerColor = FrigoBackground) {
                        val colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = FrigoAccent,
                            selectedTextColor = FrigoAccent,
                            indicatorColor = FrigoAccent.copy(alpha = 0.15f),
                            unselectedIconColor = FrigoText,
                            unselectedTextColor = FrigoText,
                        )
                        // Objects live behind Menu, so that tab lights up while it's open.
                        NavigationBarItem(
                            selected = route == HomeRoutes.OBJECTS,
                            onClick = { menuOpen = true },
                            icon = { Icon(Icons.Filled.Menu, contentDescription = null) },
                            label = { Text("Menu") },
                            colors = colors,
                        )
                        NavigationBarItem(
                            selected = route == HomeRoutes.OVERVIEW,
                            onClick = { navController.switchTab(HomeRoutes.OVERVIEW) },
                            icon = { Icon(Icons.Filled.Dashboard, contentDescription = null) },
                            label = { Text("Dashboard") },
                            colors = colors,
                        )
                        NavigationBarItem(
                            selected = route == HomeRoutes.ALARMS,
                            onClick = { navController.switchTab(HomeRoutes.ALARMS) },
                            icon = { Icon(Icons.Outlined.NotificationsNone, contentDescription = null) },
                            label = { Text("Alarmy") },
                            colors = colors,
                        )
                    }
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = HomeRoutes.OVERVIEW,
            modifier = Modifier.padding(padding),
        ) {
            composable(HomeRoutes.OVERVIEW) {
                OverviewScreen(
                    onSensorClick = { sensor ->
                        navController.navigate(HomeRoutes.sensorRoute(sensor.object_id, sensor.id, sensor.name))
                    },
                    onAlarmClick = onAlarmClick,
                )
            }
            composable(HomeRoutes.OBJECTS) {
                ObjectsScreen(onObjectClick = {
                    viewModel.selectObject(it.id)
                    navController.switchTab(HomeRoutes.OVERVIEW)
                })
            }
            composable(HomeRoutes.ALARMS) {
                DashboardScreen(isTechnician = viewModel.isTechnician, onAlarmClick = onAlarmClick)
            }
            composable(
                HomeRoutes.SENSOR,
                arguments = listOf(
                    navArgument("objectId") { type = NavType.StringType },
                    navArgument("sensorId") { type = NavType.StringType },
                    navArgument("name") { type = NavType.StringType; defaultValue = "" },
                ),
            ) {
                SensorScreen(onClose = { navController.popBackStack() })
            }
        }
    }

    if (menuOpen) {
        ModalBottomSheet(onDismissRequest = { menuOpen = false }, containerColor = FrigoSurface) {
            if (viewModel.displayName.isNotBlank()) {
                Text(
                    viewModel.displayName,
                    color = FrigoTextMuted,
                    style = MaterialTheme.typography.labelLarge,
                    modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp),
                )
            }
            MenuItem(Icons.Outlined.Apartment, "Obiekty") {
                menuOpen = false
                navController.switchTab(HomeRoutes.OBJECTS)
            }
            MenuItem(Icons.AutoMirrored.Filled.Logout, "Wyloguj") {
                menuOpen = false
                viewModel.logout(onLoggedOut)
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun MenuItem(icon: ImageVector, label: String, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 24.dp, vertical = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = FrigoAccent)
        Spacer(Modifier.width(16.dp))
        Text(label, color = FrigoText, fontSize = 17.sp)
    }
}

@Composable
private fun FrigoHeader(header: HeaderState, onAlarmsClick: () -> Unit) {
    Column(Modifier.background(FrigoBackground).windowInsetsPadding(WindowInsets.statusBars)) {
        Row(
            Modifier.fillMaxWidth().padding(start = 16.dp, end = 12.dp, top = 10.dp, bottom = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Outlined.ViewInAr, contentDescription = null, tint = FrigoAccent, modifier = Modifier.size(30.dp))
            Spacer(Modifier.width(10.dp))
            Text(
                buildAnnotatedString {
                    withStyle(SpanStyle(color = FrigoText)) { append("FRIGO") }
                    withStyle(SpanStyle(color = FrigoAccent)) { append("CORE") }
                },
                fontWeight = FontWeight.Bold,
                fontSize = 20.sp,
                modifier = Modifier.weight(1f),
            )
            val live = header.isLive()
            Pill(
                color = if (live) FrigoOk else FrigoTextMuted,
                leading = { Box(Modifier.size(8.dp).background(if (live) FrigoOk else FrigoTextMuted, CircleShape)) },
                text = if (live) "LIVE" else "OFFLINE",
            )
            VerticalDivider(Modifier.height(24.dp).padding(horizontal = 8.dp), color = FrigoOutline)
            // "ALARM" always; it fills in red (with the count) once something is open.
            Pill(
                color = FrigoCritical,
                leading = { Icon(Icons.Filled.Notifications, contentDescription = null, tint = FrigoCritical, modifier = Modifier.size(16.dp)) },
                text = if (header.openAlarms > 0) Formatters.alarmCount(header.openAlarms) else "ALARM",
                onClick = onAlarmsClick,
                filled = header.openAlarms > 0,
            )
        }
        HorizontalDivider(color = FrigoOutline)
    }
}

@Composable
private fun Pill(
    color: Color,
    leading: @Composable () -> Unit,
    text: String,
    onClick: (() -> Unit)? = null,
    filled: Boolean = false,
) {
    Row(
        Modifier
            .background(if (filled) color.copy(alpha = 0.18f) else color.copy(alpha = 0.06f), RoundedCornerShape(8.dp))
            .border(BorderStroke(1.dp, color), RoundedCornerShape(8.dp))
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 12.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        leading()
        Spacer(Modifier.width(7.dp))
        Text(text, color = color, fontSize = 14.sp, fontWeight = FontWeight.Bold)
    }
}

private fun NavHostController.switchTab(route: String) {
    navigate(route) {
        popUpTo(graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}
