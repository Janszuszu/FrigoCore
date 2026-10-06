package pl.frigocore.service.fcm

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.core.content.getSystemService
import androidx.test.core.app.ApplicationProvider
import com.google.common.truth.Truth.assertThat
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import pl.frigocore.service.R
import pl.frigocore.service.data.model.ServiceAlarmPayload
import pl.frigocore.service.ui.alarm.AlarmActivity

/** Verifies the actual OS-level shape of a SERVICE_ALARM notification — the
 * pieces Android requires for it to auto-launch AlarmActivity as a
 * full-screen alarm instead of sitting as a tap-to-open notification. */
@RunWith(RobolectricTestRunner::class)
class AlarmNotificationHelperTest {

    private val context = ApplicationProvider.getApplicationContext<android.app.Application>()

    private fun payload(alarmId: String = "alarm-1") = ServiceAlarmPayload(
        type = ServiceAlarmPayload.TYPE_SERVICE_ALARM,
        version = 1,
        alarmId = alarmId,
        assignmentId = "assignment-1",
        tier = 1,
        siteId = "site-1",
        siteName = "Chłodnia Biskupiec",
        alarmType = "HIGH_TEMPERATURE",
        severity = "CRITICAL",
        title = "ALARM KRYTYCZNY",
        message = "Temperatura powyżej progu",
        sensorName = "Chłodnia - Parownik",
        requiresAction = true,
        createdAt = "2026-08-16T12:00:00Z",
        dispatchedAt = "2026-08-16T12:00:05Z",
    )

    @Before
    fun setUp() {
        // Production creates this channel in FrigoCoreApplication.onCreate —
        // Robolectric doesn't run the real Application class, so it's
        // recreated here to match what the device actually has.
        val channel = NotificationChannel(
            context.getString(R.string.notification_channel_alarms_id),
            context.getString(R.string.notification_channel_alarms_name),
            NotificationManager.IMPORTANCE_HIGH,
        )
        context.getSystemService<NotificationManager>()?.createNotificationChannel(channel)

        // Robolectric doesn't auto-grant dangerous runtime permissions just
        // because the manifest declares them — this test is about the
        // notification's shape, not the permission gate itself (that's
        // AlarmPermissionsTest's job), so grant it explicitly.
        shadowOf(context).grantPermissions(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun shownNotification(alarmId: String): Notification {
        AlarmNotificationHelper(context).showCriticalAlarm(payload(alarmId))
        val shadowManager = shadowOf(context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
        return shadowManager.getNotification(AlarmNotificationHelper.notificationId(alarmId))
    }

    @Test
    fun `full-screen intent is attached and targets AlarmActivity`() {
        val notification = shownNotification("alarm-1")
        val fullScreenIntent = notification.fullScreenIntent
        assertThat(fullScreenIntent).isNotNull()

        val shadowPendingIntent = shadowOf(fullScreenIntent)
        val target = shadowPendingIntent.savedIntent.component
        assertThat(target?.className).isEqualTo(AlarmActivity::class.java.name)
    }

    @Test
    fun `content intent also targets AlarmActivity for the tap fallback`() {
        val notification = shownNotification("alarm-1")
        val shadowPendingIntent = shadowOf(notification.contentIntent)
        val target = shadowPendingIntent.savedIntent.component
        assertThat(target?.className).isEqualTo(AlarmActivity::class.java.name)
    }

    @Test
    fun `notification uses the critical alarm channel at high importance`() {
        val notification = shownNotification("alarm-1")
        assertThat(notification.channelId).isEqualTo(context.getString(R.string.notification_channel_alarms_id))
        assertThat(notification.priority).isEqualTo(Notification.PRIORITY_MAX)

        val channel = context.getSystemService<NotificationManager>()
            ?.getNotificationChannel(notification.channelId)
        assertThat(channel?.importance).isEqualTo(NotificationManager.IMPORTANCE_HIGH)
    }

    @Test
    fun `notification is insistent so sound and vibration repeat until dismissed`() {
        val notification = shownNotification("alarm-1")
        assertThat(notification.flags and Notification.FLAG_INSISTENT).isEqualTo(Notification.FLAG_INSISTENT)
    }

    @Test
    fun `accept and decline actions are both present`() {
        val notification = shownNotification("alarm-1")
        val actionTitles = notification.actions.map { it.title.toString() }
        assertThat(actionTitles).containsExactly(
            context.getString(R.string.action_accept),
            context.getString(R.string.action_decline),
        )
    }

    @Test
    fun `clearAlarm cancels the notification`() {
        val alarmId = "alarm-1"
        shownNotification(alarmId)
        AlarmNotificationHelper(context).clearAlarm(alarmId)

        val shadowManager = shadowOf(context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
        assertThat(shadowManager.getNotification(AlarmNotificationHelper.notificationId(alarmId))).isNull()
    }
}
