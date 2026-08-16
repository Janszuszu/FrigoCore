package pl.frigocore.service.fcm

import androidx.test.core.app.ApplicationProvider
import com.google.common.truth.Truth.assertThat
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import pl.frigocore.service.data.model.ServiceAlarmPayload

/** FCM does not guarantee exactly-once delivery — a redelivered push for
 * the same dispatch must not re-trigger the critical alarm UI/sound a
 * second time, but a genuinely new dispatch (re-escalation) must still alert. */
@RunWith(RobolectricTestRunner::class)
class AlarmDedupStoreTest {

    private val context = ApplicationProvider.getApplicationContext<android.app.Application>()
    private val store = AlarmDedupStore(context)

    private fun payload(alarmId: String, assignmentId: String) = ServiceAlarmPayload(
        type = ServiceAlarmPayload.TYPE_SERVICE_ALARM,
        version = 1,
        alarmId = alarmId,
        assignmentId = assignmentId,
        tier = 1,
        siteId = "site-1",
        siteName = "Test Site",
        alarmType = "HIGH_TEMPERATURE",
        severity = "CRITICAL",
        title = "ALARM KRYTYCZNY",
        message = "test",
        sensorName = "Sensor Test",
        requiresAction = true,
        createdAt = "2026-08-16T12:00:00Z",
        dispatchedAt = "2026-08-16T12:00:05Z",
    )

    @Test
    fun `first delivery of an assignment is not a duplicate`() {
        val p = payload("alarm-1", "assignment-1")
        assertThat(store.isDuplicate(p)).isFalse()
    }

    @Test
    fun `redelivery of the same assignment is detected as duplicate`() {
        val p = payload("alarm-1", "assignment-1")
        store.markShown(p)
        assertThat(store.isDuplicate(p)).isTrue()
    }

    @Test
    fun `a new assignment for the same alarm (re-escalation) is not a duplicate`() {
        val first = payload("alarm-1", "assignment-1")
        val escalated = payload("alarm-1", "assignment-2")
        store.markShown(first)
        assertThat(store.isDuplicate(escalated)).isFalse()
    }

    @Test
    fun `clearing an alarm resets duplicate tracking`() {
        val p = payload("alarm-1", "assignment-1")
        store.markShown(p)
        store.clear("alarm-1")
        assertThat(store.isDuplicate(p)).isFalse()
    }
}
