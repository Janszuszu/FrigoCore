package pl.frigocore.service.permissions

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.getSystemService

/**
 * The two OS-level gates that decide whether a SERVICE_ALARM push actually
 * reaches the technician as an automatic full-screen alarm: the app-level
 * notifications toggle, and — Android 14+ only — the separate full-screen-intent
 * special permission. Both can be denied independently of the manifest
 * declarations, so the alarm pipeline is only as reliable as this check.
 */
object AlarmPermissions {

    fun notificationsEnabled(context: Context): Boolean =
        NotificationManagerCompat.from(context).areNotificationsEnabled()

    /** Full-screen-intent eligibility is only gated starting Android 14
     * (API 34); on older versions the manifest permission alone is enough. */
    fun canUseFullScreenIntent(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return true
        return context.getSystemService<NotificationManager>()?.canUseFullScreenIntent() ?: true
    }

    fun fullScreenIntentSettingsIntent(context: Context): Intent =
        Intent(
            Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT,
            Uri.parse("package:${context.packageName}"),
        )

    fun appNotificationSettingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
            .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
}
