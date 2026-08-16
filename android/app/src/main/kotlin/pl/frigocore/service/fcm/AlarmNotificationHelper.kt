package pl.frigocore.service.fcm

import android.Manifest
import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import dagger.hilt.android.qualifiers.ApplicationContext
import pl.frigocore.service.R
import pl.frigocore.service.data.model.ServiceAlarmPayload
import pl.frigocore.service.ui.alarm.AlarmActivity
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Builds and shows the critical SERVICE_ALARM notification: a high-priority,
 * full-screen-intent notification identified by the alarm's own id so a
 * re-delivered push (retry, duplicate FCM delivery) updates the same
 * notification instead of stacking duplicates.
 */
@Singleton
class AlarmNotificationHelper @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    fun showCriticalAlarm(payload: ServiceAlarmPayload) {
        val fullScreenIntent = AlarmActivity.newIntent(context, payload)
        val fullScreenPendingIntent = PendingIntent.getActivity(
            context,
            notificationId(payload.alarmId),
            fullScreenIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val contentPendingIntent = PendingIntent.getActivity(
            context,
            notificationId(payload.alarmId) + 1,
            fullScreenIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val acceptIntent = AlarmActionReceiver.newIntent(context, payload, AlarmActionReceiver.ACTION_OPEN_ACCEPT)
        val acceptPendingIntent = PendingIntent.getBroadcast(
            context,
            notificationId(payload.alarmId) + 2,
            acceptIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val declineIntent = AlarmActionReceiver.newIntent(context, payload, AlarmActionReceiver.ACTION_OPEN_DECLINE)
        val declinePendingIntent = PendingIntent.getBroadcast(
            context,
            notificationId(payload.alarmId) + 3,
            declineIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val notification = NotificationCompat.Builder(context, context.getString(R.string.notification_channel_alarms_id))
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(payload.title)
            .setContentText("${payload.siteName} — ${payload.message}")
            .setStyle(NotificationCompat.BigTextStyle().bigText("${payload.siteName}\n${payload.message}"))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(false)
            .setOngoing(true)
            .setFullScreenIntent(fullScreenPendingIntent, true)
            .setContentIntent(contentPendingIntent)
            .addAction(0, context.getString(R.string.action_accept), acceptPendingIntent)
            .addAction(0, context.getString(R.string.action_decline), declinePendingIntent)
            .build()
            .apply { flags = flags or Notification.FLAG_INSISTENT }

        // The technician declining POST_NOTIFICATIONS (Android 13+) must not
        // crash this path, and must not be worked around — the full-screen
        // intent above still fires when the OS allows it regardless.
        val hasPermission = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        if (hasPermission) {
            NotificationManagerCompat.from(context).notify(notificationId(payload.alarmId), notification)
        } else {
            Log.w(TAG, "POST_NOTIFICATIONS not granted — cannot show alarm notification for ${payload.alarmId}")
        }
    }

    fun clearAlarm(alarmId: String) {
        NotificationManagerCompat.from(context).cancel(notificationId(alarmId))
    }

    companion object {
        /** Stable per-alarm notification id so re-delivery of the same
         * alarm_id updates rather than duplicates the tray entry. */
        fun notificationId(alarmId: String): Int = ALARM_NOTIFICATION_BASE + (alarmId.hashCode() and 0x00FFFFFF)

        private const val ALARM_NOTIFICATION_BASE = 90_000
        private const val TAG = "AlarmNotificationHelper"
    }
}
