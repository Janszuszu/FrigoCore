package pl.frigocore.service.ui.alarm

import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.content.getSystemService
import dagger.hilt.android.AndroidEntryPoint
import pl.frigocore.service.data.model.ServiceAlarmPayload
import pl.frigocore.service.fcm.getAlarmPayloadExtra
import pl.frigocore.service.fcm.putAlarmPayloadExtra
import pl.frigocore.service.ui.theme.FrigoCoreTheme

/**
 * Dedicated full-screen screen for a critical SERVICE_ALARM, launched either
 * by the notification's full-screen intent (device permitting — see
 * AndroidManifest for USE_FULL_SCREEN_INTENT) or by tapping the heads-up
 * notification / its action buttons. Uses the documented alarm-clock-style
 * APIs (setShowWhenLocked/setTurnScreenOn) rather than any lower-level
 * window trick, and never overrides a user-declined system permission.
 */
@AndroidEntryPoint
class AlarmActivity : ComponentActivity() {

    private val viewModel: AlarmViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        }
        getSystemService<KeyguardManager>()?.requestDismissKeyguard(this, null)

        val payload = intent.getAlarmPayloadExtra()
        val pendingAction = intent.getStringExtra(EXTRA_PENDING_ACTION)?.let { PendingAction.valueOf(it) }
        if (payload != null) {
            viewModel.initialize(payload, pendingAction)
        }

        setContent {
            val uiState by viewModel.uiState.collectAsState()
            FrigoCoreTheme {
                AlarmScreen(
                    uiState = uiState,
                    onAccept = viewModel::accept,
                    onDecline = viewModel::decline,
                    onEnRoute = viewModel::markEnRoute,
                    onResolve = viewModel::resolve,
                    onDismissError = viewModel::dismissError,
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val payload = intent.getAlarmPayloadExtra() ?: return
        val pendingAction = intent.getStringExtra(EXTRA_PENDING_ACTION)?.let { PendingAction.valueOf(it) }
        viewModel.initialize(payload, pendingAction)
    }

    companion object {
        private const val EXTRA_PENDING_ACTION = "pl.frigocore.service.extra.PENDING_ACTION"

        fun newIntent(context: Context, payload: ServiceAlarmPayload, pendingAction: PendingAction? = null): Intent =
            Intent(context, AlarmActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
                putAlarmPayloadExtra(payload)
                pendingAction?.let { putExtra(EXTRA_PENDING_ACTION, it.name) }
            }
    }
}
