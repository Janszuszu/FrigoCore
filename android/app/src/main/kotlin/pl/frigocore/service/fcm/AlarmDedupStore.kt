package pl.frigocore.service.fcm

import android.content.Context
import androidx.core.content.edit
import dagger.hilt.android.qualifiers.ApplicationContext
import pl.frigocore.service.data.model.ServiceAlarmPayload
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Tracks the last assignment_id shown per alarm_id. FCM does not guarantee
 * exactly-once delivery (retries, duplicate deliveries after a connectivity
 * blip are normal) — without this, the same dispatch could re-post the
 * notification and re-fire the full-screen intent + alarm sound every time
 * it is redelivered instead of once per actual dispatch.
 */
@Singleton
class AlarmDedupStore @Inject constructor(@ApplicationContext context: Context) {

    private val prefs = context.getSharedPreferences("frigocore_alarm_dedup", Context.MODE_PRIVATE)

    /** True if this exact assignment (not just this alarm) was already
     * shown — a *new* assignment for the same alarm (re-escalation) must
     * still alert again. */
    fun isDuplicate(payload: ServiceAlarmPayload): Boolean =
        prefs.getString(payload.alarmId, null) == payload.assignmentId

    fun markShown(payload: ServiceAlarmPayload) {
        prefs.edit { putString(payload.alarmId, payload.assignmentId) }
    }

    fun clear(alarmId: String) {
        prefs.edit { remove(alarmId) }
    }
}
