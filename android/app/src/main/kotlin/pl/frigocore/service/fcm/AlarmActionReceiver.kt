package pl.frigocore.service.fcm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import pl.frigocore.service.data.model.ServiceAlarmPayload
import pl.frigocore.service.ui.alarm.AlarmActivity
import pl.frigocore.service.ui.alarm.PendingAction

/**
 * Handles the notification's direct action buttons. A background
 * BroadcastReceiver cannot itself perform a confirmed, user-visible
 * accept/decline (a critical action must show its own failure state, not
 * fail silently off-screen) — so it hands off to AlarmActivity, pre-armed
 * to fire the requested action immediately on launch.
 */
class AlarmActionReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val payload = intent.getAlarmPayloadExtra() ?: return
        val pendingAction = when (intent.action) {
            ACTION_OPEN_ACCEPT -> PendingAction.ACCEPT
            ACTION_OPEN_DECLINE -> PendingAction.DECLINE
            else -> null
        }
        val activityIntent = AlarmActivity.newIntent(context, payload, pendingAction)
        context.startActivity(activityIntent)
    }

    companion object {
        const val ACTION_OPEN_ACCEPT = "pl.frigocore.service.action.OPEN_ACCEPT"
        const val ACTION_OPEN_DECLINE = "pl.frigocore.service.action.OPEN_DECLINE"

        fun newIntent(context: Context, payload: ServiceAlarmPayload, action: String): Intent =
            Intent(context, AlarmActionReceiver::class.java).apply {
                this.action = action
                putAlarmPayloadExtra(payload)
            }
    }
}
