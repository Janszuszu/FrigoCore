package pl.frigocore.service

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.platform.LocalContext
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import dagger.hilt.android.AndroidEntryPoint
import pl.frigocore.service.data.local.SessionExpiredNotifier
import pl.frigocore.service.data.model.ServiceAlarmPayload
import pl.frigocore.service.data.repository.AuthRepository
import pl.frigocore.service.ui.alarm.AlarmActivity
import pl.frigocore.service.ui.dashboard.DashboardScreen
import pl.frigocore.service.ui.login.LoginScreen
import pl.frigocore.service.ui.theme.FrigoCoreTheme
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var authRepository: AuthRepository
    @Inject lateinit var sessionExpiredNotifier: SessionExpiredNotifier

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)

        setContent {
            FrigoCoreTheme {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    val requestNotificationPermission = rememberLauncherForActivityResult(
                        ActivityResultContracts.RequestPermission(),
                    ) { }
                    // A denied SERVICE_ALARM notification is a missed critical
                    // alarm, so this is asked for immediately rather than
                    // waiting for a feature that "needs" it.
                    LaunchedEffect(Unit) {
                        requestNotificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                }
                FrigoCoreNavHost(
                    startLoggedIn = authRepository.isLoggedIn,
                    sessionExpiredNotifier = sessionExpiredNotifier,
                )
            }
        }
    }
}

private object Routes {
    const val LOGIN = "login"
    const val DASHBOARD = "dashboard"
}

@Composable
private fun FrigoCoreNavHost(
    startLoggedIn: Boolean,
    sessionExpiredNotifier: SessionExpiredNotifier,
) {
    val navController: NavHostController = rememberNavController()

    // An expired/rejected token can be discovered from any authenticated
    // screen — force everyone back to Login rather than letting each screen
    // handle its own 401 independently.
    LaunchedEffect(Unit) {
        sessionExpiredNotifier.events.collect {
            navController.navigate(Routes.LOGIN) {
                popUpTo(0) { inclusive = true }
            }
        }
    }

    NavHost(
        navController = navController,
        startDestination = if (startLoggedIn) Routes.DASHBOARD else Routes.LOGIN,
    ) {
        composable(Routes.LOGIN) {
            LoginScreen(
                onLoggedIn = {
                    navController.navigate(Routes.DASHBOARD) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
            )
        }
        composable(Routes.DASHBOARD) {
            val context = LocalContext.current
            DashboardScreen(
                onAlarmClick = { alarmId ->
                    // Reuses the same full-screen alarm UI as a push —
                    // AlarmViewModel.loadDetail() fetches the authoritative
                    // AlarmResponse, so this placeholder payload only needs
                    // a valid alarm_id to seed it.
                    val payload = ServiceAlarmPayload(
                        type = ServiceAlarmPayload.TYPE_SERVICE_ALARM,
                        version = 1,
                        alarmId = alarmId,
                        assignmentId = "",
                        tier = 0,
                        siteId = "",
                        siteName = "",
                        alarmType = "",
                        severity = "",
                        title = "",
                        message = "",
                        sensorName = "",
                        requiresAction = true,
                        createdAt = "",
                        dispatchedAt = "",
                    )
                    context.startActivity(AlarmActivity.newIntent(context, payload))
                },
                onLoggedOut = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                },
            )
        }
    }
}
