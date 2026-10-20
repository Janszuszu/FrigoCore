package pl.frigocore.service.ui.home

import pl.frigocore.service.ui.theme.TabularNumbers
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsIgnoringVisibility
import androidx.compose.foundation.layout.statusBarsIgnoringVisibility
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.platform.LocalContext
import androidx.hilt.navigation.HiltViewModelFactory
import androidx.lifecycle.HasDefaultViewModelProviderFactory
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewmodel.CreationExtras
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import pl.frigocore.service.ui.sensor.SensorViewModel
import pl.frigocore.service.ui.reports.ReportsScreen
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.outlined.Apartment
import androidx.compose.material.icons.outlined.Assessment
import androidx.compose.material.icons.outlined.ElectricMeter
import androidx.compose.material.icons.outlined.Kitchen
import androidx.compose.material.icons.outlined.Hvac
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
import androidx.compose.runtime.saveable.rememberSaveable
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
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import pl.frigocore.service.data.local.SelectedObjectStore
import pl.frigocore.service.data.model.UserRole
import pl.frigocore.service.data.repository.AuthRepository
import pl.frigocore.service.ui.aggregates.AggregatesScreen
import pl.frigocore.service.ui.dashboard.DashboardScreen
import pl.frigocore.service.ui.meters.MetersScreen
import pl.frigocore.service.ui.objects.ObjectsScreen
import pl.frigocore.service.ui.overview.OverviewScreen
import pl.frigocore.service.ui.receivers.ReceiversScreen
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
    /** Urządzenia: receivers, aggregates and meters, swiped between (DevicesPager). */
    const val DEVICES = "devices"
    const val OBJECTS = "objects"
    const val ALARMS = "alarms"
    const val REPORTS = "reports"
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun HomeScreen(
    onAlarmClick: (String) -> Unit,
    onLoggedOut: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val navController: NavHostController = rememberNavController()
    val backStack by navController.currentBackStackEntryAsState()
    val route = backStack?.destination?.route
    // The full-screen chart slides over everything: "objectId/sensorId", null when shut.
    var chart by rememberSaveable { mutableStateOf<String?>(null) }
    val openChart = { objectId: String, sensorId: String -> chart = "$objectId/$sensorId" }
    var menuOpen by remember { mutableStateOf(false) }
    // The device group shown (receivers, aggregates, meters) — kept across tabs and object picks.
    var devicesPage by rememberSaveable { mutableStateOf(0) }

    Box(Modifier.fillMaxSize()) {
    Scaffold(
        containerColor = FrigoBackground,
        topBar = { FrigoHeader() },
        bottomBar = {
            run {
                Column {
                    HorizontalDivider(color = FrigoOutline)
                    // Hidden bars behind the chart must not shift the screen under it.
                    NavigationBar(containerColor = FrigoBackground, windowInsets = WindowInsets.navigationBarsIgnoringVisibility) {
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
                        // Devices are grouped by type, swiped between on the page itself.
                        NavigationBarItem(
                            selected = route == HomeRoutes.DEVICES,
                            onClick = { navController.switchTab(HomeRoutes.DEVICES) },
                            icon = { Icon(Icons.Outlined.Kitchen, contentDescription = null) },
                            label = { Text("Urządzenia") },
                            colors = colors,
                        )
                        NavigationBarItem(
                            selected = route == HomeRoutes.REPORTS,
                            onClick = { navController.switchTab(HomeRoutes.REPORTS) },
                            icon = { Icon(Icons.Outlined.Assessment, contentDescription = null) },
                            label = { Text("Raport") },
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
            startDestination = HomeRoutes.DEVICES,
            modifier = Modifier.padding(padding),
        ) {
            composable(HomeRoutes.DEVICES) {
                DevicesPager(
                    page = devicesPage,
                    onPage = { devicesPage = it },
                    receivers = {
                        ReceiversScreen(
                            onOpenChart = { objectId, sensorId, _ -> openChart(objectId, sensorId) },
                            fallback = {
                                OverviewScreen(
                                    onSensorClick = { sensor ->
                                        openChart(sensor.object_id, sensor.id)
                                    },
                                    onAlarmClick = onAlarmClick,
                                )
                            },
                        )
                    },
                    aggregates = {
                        AggregatesScreen(onSensorClick = { sensor ->
                            openChart(sensor.object_id, sensor.id)
                        })
                    },
                    meters = { MetersScreen() },
                )
            }
            composable(HomeRoutes.OBJECTS) {
                ObjectsScreen(onObjectClick = {
                    viewModel.selectObject(it.id)
                    navController.switchTab(HomeRoutes.DEVICES)
                })
            }
            composable(HomeRoutes.REPORTS) {
                ReportsScreen()
            }
            composable(HomeRoutes.ALARMS) {
                DashboardScreen(isTechnician = viewModel.isTechnician, onAlarmClick = onAlarmClick)
            }
        }
    }

    BackHandler(enabled = chart != null) { chart = null }
    // Keeps the last sensor on screen while the chart slides back out.
    var shown by remember { mutableStateOf(chart) }
    if (chart != null) shown = chart
    AnimatedVisibility(
        visible = chart != null,
        enter = slideInHorizontally { -it },
        exit = slideOutHorizontally { -it },
    ) {
        val (objectId, sensorId) = shown.orEmpty().split("/", limit = 2).let { it.first() to it.getOrElse(1) { "" } }
        ChartViewModels {
            val chartViewModel: SensorViewModel = hiltViewModel()
            LaunchedEffect(objectId, sensorId) { chartViewModel.open(objectId, sensorId) }
            SensorScreen(onClose = { chart = null }, viewModel = chartViewModel)
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
        Text(label, color = FrigoText, fontSize = 17.sp, modifier = Modifier.weight(1f))
    }
}

private val clockFormat = DateTimeFormatter.ofPattern("HH:mm:ss")

/** Logo on the left, live clock on the right. */
@OptIn(ExperimentalLayoutApi::class)
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
    Column(Modifier.background(FrigoBackground).windowInsetsPadding(WindowInsets.statusBarsIgnoringVisibility)) {
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
                fontSize = 20.sp,
                maxLines = 1,
                softWrap = false,
                modifier = Modifier.weight(1f),
            )
            Text(local.format(clockFormat), color = FrigoAccent, fontSize = 16.sp, maxLines = 1, fontWeight = FontWeight.Bold, style = TabularNumbers)
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

/** A view-model scope of its own for the chart overlay, cleared when the
 * chart has slid away, so every opening starts on the current 24 hours. */
@Composable
private fun ChartViewModels(content: @Composable () -> Unit) {
    val parent = checkNotNull(LocalViewModelStoreOwner.current)
    val context = LocalContext.current
    val owner = remember(parent) {
        object : ViewModelStoreOwner, HasDefaultViewModelProviderFactory {
            override val viewModelStore = ViewModelStore()
            override val defaultViewModelProviderFactory: ViewModelProvider.Factory =
                HiltViewModelFactory(context, (parent as HasDefaultViewModelProviderFactory).defaultViewModelProviderFactory)
            override val defaultViewModelCreationExtras: CreationExtras
                get() = (parent as HasDefaultViewModelProviderFactory).defaultViewModelCreationExtras
        }
    }
    DisposableEffect(owner) { onDispose { owner.viewModelStore.clear() } }
    CompositionLocalProvider(LocalViewModelStoreOwner provides owner, content = content)
}
