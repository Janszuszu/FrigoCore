package pl.frigocore.service.ui.home

import android.net.Uri
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material.icons.filled.Storefront
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
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
import kotlinx.coroutines.launch
import pl.frigocore.service.data.model.UserRole
import pl.frigocore.service.data.repository.AuthRepository
import pl.frigocore.service.ui.dashboard.DashboardScreen
import pl.frigocore.service.ui.objects.ObjectDetailScreen
import pl.frigocore.service.ui.objects.ObjectsScreen
import pl.frigocore.service.ui.sensor.SensorScreen
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {
    /** Owners (`user` role) only watch their objects; everyone else is
     * service staff who can act on alarms. */
    val isTechnician: Boolean = authRepository.currentUser?.role != UserRole.USER
    val displayName: String = authRepository.currentUser?.let { it.full_name.ifBlank { it.username } }.orEmpty()

    fun logout(onDone: () -> Unit) {
        viewModelScope.launch {
            authRepository.logout()
            onDone()
        }
    }
}

private object HomeRoutes {
    const val OBJECTS = "objects"
    const val ALARMS = "alarms"
    const val OBJECT = "object/{objectId}?name={name}"
    const val SENSOR = "sensor/{objectId}/{sensorId}?name={name}"

    fun objectRoute(id: String, name: String) = "object/$id?name=${Uri.encode(name)}"
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
    val isTopLevel = route == HomeRoutes.OBJECTS || route == HomeRoutes.ALARMS || route == null
    val title = when (route) {
        HomeRoutes.ALARMS -> "Alarmy"
        HomeRoutes.OBJECT, HomeRoutes.SENSOR -> backStack?.arguments?.getString("name").orEmpty()
        else -> "Obiekty"
    }
    var menuOpen by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    if (!isTopLevel) {
                        IconButton(onClick = { navController.popBackStack() }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Wstecz")
                        }
                    }
                },
                actions = {
                    IconButton(onClick = { menuOpen = true }) {
                        Icon(Icons.Filled.MoreVert, contentDescription = "Menu")
                    }
                    DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                        if (viewModel.displayName.isNotBlank()) {
                            DropdownMenuItem(text = { Text(viewModel.displayName) }, onClick = {}, enabled = false)
                        }
                        DropdownMenuItem(
                            text = { Text("Wyloguj") },
                            leadingIcon = { Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null) },
                            onClick = {
                                menuOpen = false
                                viewModel.logout(onLoggedOut)
                            },
                        )
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                val objectsSelected = route != HomeRoutes.ALARMS
                NavigationBarItem(
                    selected = objectsSelected,
                    onClick = {
                        // Re-tapping the current tab returns to the object list.
                        if (objectsSelected) navController.popBackStack(HomeRoutes.OBJECTS, inclusive = false)
                        else navController.switchTab(HomeRoutes.OBJECTS)
                    },
                    icon = { Icon(Icons.Filled.Storefront, contentDescription = null) },
                    label = { Text("Obiekty") },
                )
                NavigationBarItem(
                    selected = !objectsSelected,
                    onClick = { navController.switchTab(HomeRoutes.ALARMS) },
                    icon = { Icon(Icons.Filled.NotificationsActive, contentDescription = null) },
                    label = { Text("Alarmy") },
                )
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = HomeRoutes.OBJECTS,
            modifier = Modifier.padding(padding),
        ) {
            composable(HomeRoutes.OBJECTS) {
                ObjectsScreen(onObjectClick = { navController.navigate(HomeRoutes.objectRoute(it.id, it.name)) })
            }
            composable(HomeRoutes.ALARMS) {
                DashboardScreen(isTechnician = viewModel.isTechnician, onAlarmClick = onAlarmClick)
            }
            composable(
                HomeRoutes.OBJECT,
                arguments = listOf(
                    navArgument("objectId") { type = NavType.StringType },
                    navArgument("name") { type = NavType.StringType; defaultValue = "" },
                ),
            ) {
                ObjectDetailScreen(
                    onSensorClick = { sensor ->
                        navController.navigate(HomeRoutes.sensorRoute(sensor.object_id, sensor.id, sensor.name))
                    },
                    onAlarmClick = onAlarmClick,
                )
            }
            composable(
                HomeRoutes.SENSOR,
                arguments = listOf(
                    navArgument("objectId") { type = NavType.StringType },
                    navArgument("sensorId") { type = NavType.StringType },
                    navArgument("name") { type = NavType.StringType; defaultValue = "" },
                ),
            ) {
                SensorScreen()
            }
        }
    }
}

private fun NavHostController.switchTab(route: String) {
    navigate(route) {
        popUpTo(graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}
