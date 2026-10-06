package pl.frigocore.service.data.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class ClientAlarmPayloadTest {

    @Test
    fun `parses backend CLIENT_ALARM payload`() {
        val payload = ClientAlarmPayload.fromDataMap(
            mapOf(
                "type" to "CLIENT_ALARM",
                "version" to "1",
                "event" to "en_route",
                "alarm_id" to "a1",
                "site_id" to "o1",
                "site_name" to "Chłodnia A",
                "alarm_type" to "HIGH_TEMPERATURE",
                "title" to "Serwis w drodze",
                "message" to "Serwisant jedzie na obiekt.",
                "sensor_name" to "Komora",
                "created_at" to "2026-10-05T10:00:00+00:00",
            ),
        )!!
        assertEquals(ClientAlarmPayload.EVENT_EN_ROUTE, payload.event)
        assertEquals("Chłodnia A", payload.siteName)
        val seed = payload.toServiceAlarmPayload()
        assertEquals("a1", seed.alarmId)
        assertFalse(seed.requiresAction)
    }

    @Test
    fun `rejects other payload types and missing alarm id`() {
        assertNull(ClientAlarmPayload.fromDataMap(mapOf("type" to "SERVICE_ALARM", "alarm_id" to "a1")))
        assertNull(ClientAlarmPayload.fromDataMap(mapOf("type" to "CLIENT_ALARM")))
    }

    @Test
    fun `service alarm parser ignores client payloads`() {
        assertNull(ServiceAlarmPayload.fromDataMap(mapOf("type" to "CLIENT_ALARM", "alarm_id" to "a1", "site_id" to "o1")))
    }
}
