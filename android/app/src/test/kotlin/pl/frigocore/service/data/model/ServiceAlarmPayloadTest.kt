package pl.frigocore.service.data.model

import com.google.common.truth.Truth.assertThat
import org.junit.Test

/** SERVICE_ALARM payload parsing — mirrors
 * backend/app/services/notification_engine.py:build_service_alarm_payload,
 * whose values FCM stringifies before delivery (see firebase_client.send_to_token). */
class ServiceAlarmPayloadTest {

    private fun rawPayload(overrides: Map<String, String> = emptyMap()): Map<String, String> = mapOf(
        "type" to "SERVICE_ALARM",
        "version" to "1",
        "alarm_id" to "alarm-123",
        "assignment_id" to "assignment-456",
        "tier" to "1",
        "site_id" to "site-789",
        "site_name" to "Kotlety z Biskupca",
        "alarm_type" to "HIGH_TEMPERATURE",
        "severity" to "CRITICAL",
        "title" to "ALARM KRYTYCZNY",
        "message" to "Temperatura przekroczona",
        // Python's str(True) — not JSON "true".
        "requires_action" to "True",
        "created_at" to "2026-08-16T12:00:00+00:00",
    ) + overrides

    @Test
    fun `parses a well-formed SERVICE_ALARM payload`() {
        val payload = ServiceAlarmPayload.fromDataMap(rawPayload())

        assertThat(payload).isNotNull()
        assertThat(payload!!.alarmId).isEqualTo("alarm-123")
        assertThat(payload.assignmentId).isEqualTo("assignment-456")
        assertThat(payload.tier).isEqualTo(1)
        assertThat(payload.siteName).isEqualTo("Kotlety z Biskupca")
        assertThat(payload.requiresAction).isTrue()
    }

    @Test
    fun `parses Python-style capitalized True for requires_action`() {
        val payload = ServiceAlarmPayload.fromDataMap(rawPayload(mapOf("requires_action" to "True")))
        assertThat(payload!!.requiresAction).isTrue()
    }

    @Test
    fun `parses Python-style capitalized False for requires_action`() {
        val payload = ServiceAlarmPayload.fromDataMap(rawPayload(mapOf("requires_action" to "False")))
        assertThat(payload!!.requiresAction).isFalse()
    }

    @Test
    fun `returns null for a non-SERVICE_ALARM type`() {
        val payload = ServiceAlarmPayload.fromDataMap(rawPayload(mapOf("type" to "OTHER")))
        assertThat(payload).isNull()
    }

    @Test
    fun `returns null when alarm_id is missing`() {
        val data = rawPayload().toMutableMap()
        data.remove("alarm_id")
        assertThat(ServiceAlarmPayload.fromDataMap(data)).isNull()
    }

    @Test
    fun `returns null when assignment_id is missing`() {
        val data = rawPayload().toMutableMap()
        data.remove("assignment_id")
        assertThat(ServiceAlarmPayload.fromDataMap(data)).isNull()
    }

    @Test
    fun `falls back gracefully on malformed numeric fields`() {
        val payload = ServiceAlarmPayload.fromDataMap(rawPayload(mapOf("tier" to "not-a-number")))
        assertThat(payload).isNotNull()
        assertThat(payload!!.tier).isEqualTo(1)
    }

    @Test
    fun `returns null for a completely empty payload`() {
        assertThat(ServiceAlarmPayload.fromDataMap(emptyMap())).isNull()
    }
}
