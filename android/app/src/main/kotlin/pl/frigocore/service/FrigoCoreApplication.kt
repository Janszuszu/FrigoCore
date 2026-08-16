package pl.frigocore.service

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import androidx.core.content.getSystemService
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class FrigoCoreApplication : Application() {

    override fun onCreate() {
        super.onCreate()
        createAlarmNotificationChannel()
    }

    /**
     * A dedicated high-importance channel for SERVICE_ALARM pushes, created
     * once at process start. Importance/sound/vibration are set on the
     * channel itself (Android ignores per-notification overrides once a
     * channel exists), so this is the one place that controls how loud and
     * insistent a critical alarm is allowed to be.
     */
    private fun createAlarmNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        val alarmSound = RingtoneManager.getActualDefaultRingtoneUri(this, RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
        val audioAttributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ALARM)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()

        val channel = NotificationChannel(
            getString(R.string.notification_channel_alarms_id),
            getString(R.string.notification_channel_alarms_name),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = getString(R.string.notification_channel_alarms_description)
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 800, 400, 800, 400, 800)
            enableLights(true)
            setBypassDnd(true)
            lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
            setSound(alarmSound, audioAttributes)
        }

        getSystemService<NotificationManager>()?.createNotificationChannel(channel)
    }
}
