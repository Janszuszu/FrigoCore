package pl.frigocore.service.fcm

import android.content.Intent
import com.google.common.truth.Truth.assertThat
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import pl.frigocore.service.data.model.ServiceAlarmPayload

/** Covers alarm state restoration through the notification -> receiver ->
 * AlarmActivity handoff (process death between tapping the notification and
 * the activity actually starting is normal on Android — the payload must
 * survive an Intent round-trip intact). */
@RunWith(RobolectricTestRunner::class)
class AlarmPayloadIntentExtrasTest {

    private val payload = ServiceAlarmPayload(
        type = ServiceAlarmPayload.TYPE_SERVICE_ALARM,
        version = 2,
        alarmId = "alarm-abc",
        assignmentId = "assignment-def",
        tier = 3,
        siteId = "site-xyz",
        siteName = "Chłodnia Nr 2",
        alarmType = "LOW_TEMPERATURE",
        severity = "CRITICAL",
        title = "ALARM KRYTYCZNY",
        message = "Temperatura poniżej progu",
        sensorName = "Mroznia - Parownik",
        requiresAction = true,
        createdAt = "2026-08-16T09:30:00+00:00",
        dispatchedAt = "2026-08-16T09:30:05+00:00",
    )

    @Test
    fun `payload round-trips through an Intent unchanged`() {
        val intent = Intent().putAlarmPayloadExtra(payload)

        val restored = intent.getAlarmPayloadExtra()

        assertThat(restored).isEqualTo(payload)
    }

    @Test
    fun `missing required extras restore as null rather than a partial payload`() {
        val intent = Intent()
        assertThat(intent.getAlarmPayloadExtra()).isNull()
    }
}
