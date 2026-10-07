package pl.frigocore.service.ui.home

import pl.frigocore.service.ui.theme.TabularNumbers
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Menu
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import pl.frigocore.service.data.local.SelectedObjectStore
import pl.frigocore.service.data.model.UserRole
import pl.frigocore.service.data.repository.AuthRepository
import pl.frigocore.service.ui.dashboard.DashboardScreen
import pl.frigocore.service.ui.objects.ObjectsScreen
import pl.frigocore.service.ui.overview.OverviewScreen
import pl.frigocore.service.ui.sensor.SensorScreen
import pl.frigocore.service.ui.theme.FrigoAccent
import pl.frigocore.service.ui.theme.FrigoBackground
import pl.frigocore.service.ui.theme.FrigoOutline
import pl.frigocore.service.ui.theme.FrigoSurface
import pl.frigocore.service.ui.theme.FrigoText
import pl.frigocore.service.ui.theme.FrigoTextMuted
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val selectedObjectStore: SelectedObjectStore,
) : ViewModel() {
    /** Owners (`user` role) only watch their objects; everyone else is
     * service staff who can act on alarms. */
    val isTechnician: Boolean = authRepository.currentUser?.role != UserRole.USER
    val displayName: String = authRepository.currentUser?.let { it.full_name.ifBlank { it.username } }.orEmpty()

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
    var menuOpen by remember { mutableStateOf(false) }

    Scaffold(
        containerColor = FrigoBackground,
        topBar = {
            if (chrome) FrigoHeader()
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

private val dateFormat = DateTimeFormatter.ofPattern("d.MM.yyyy")
private val clockFormat = DateTimeFormatter.ofPattern("HH:mm:ss")

/** Logo on the left, live date and clock on the right. */
@Composable
private fun FrigoHeader() {
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            now = Instant.now()
            delay(1_000)
        }
    }
    val local = now.atZone(ZoneId.systemDefault())
    Column(Modifier.background(FrigoBackground).windowInsetsPadding(WindowInsets.statusBars)) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
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
                fontSize = 22.sp,
                modifier = Modifier.weight(1f),
            )
            Text(local.format(dateFormat), color = FrigoTextMuted, fontSize = 18.sp, style = TabularNumbers)
            Spacer(Modifier.width(10.dp))
            Text(local.format(clockFormat), color = FrigoText, fontSize = 18.sp, fontWeight = FontWeight.Bold, style = TabularNumbers)
        }
        HorizontalDivider(color = FrigoOutline)
    }
}

private fun NavHostController.switchTab(route: String) {
    navigate(route) {
        popUpTo(graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}
