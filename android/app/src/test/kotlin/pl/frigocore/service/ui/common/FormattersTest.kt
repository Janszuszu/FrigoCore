package pl.frigocore.service.ui.common

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import pl.frigocore.service.data.model.SensorResponse
import java.time.Instant
import java.time.ZoneOffset

class FormattersTest {

    private val now = Instant.parse("2026-10-05T12:00:00Z")

    @Test
    fun `parses offset and naive UTC timestamps`() {
        assertEquals(Instant.parse("2026-10-05T10:00:00.123456Z"), Formatters.parseInstant("2026-10-05T12:00:00.123456+02:00"))
        assertEquals(Instant.parse("2026-10-05T10:00:00Z"), Formatters.parseInstant("2026-10-05T10:00:00"))
        assertNull(Formatters.parseInstant("not a date"))
        assertNull(Formatters.parseInstant(null))
    }

    @Test
    fun `formats date time in the given zone`() {
        assertEquals("05.10 12:30", Formatters.dateTime("2026-10-05T10:30:00Z", ZoneOffset.ofHours(2)))
        assertEquals("—", Formatters.dateTime(null))
    }

    @Test
    fun `temperature uses Polish decimal comma`() {
        assertEquals("-18,4°C", Formatters.temperature(-18.44))
        assertEquals("—", Formatters.temperature(null))
    }

    @Test
    fun `relative time buckets`() {
        assertEquals("przed chwilą", Formatters.ago("2026-10-05T11:59:30Z", now))
        assertEquals("5 min temu", Formatters.ago("2026-10-05T11:55:00Z", now))
        assertEquals("3 godz. temu", Formatters.ago("2026-10-05T09:00:00Z", now))
        assertEquals("2 dni temu", Formatters.ago("2026-10-03T11:00:00Z", now))
        assertEquals("brak danych", Formatters.ago(null, now))
    }

    @Test
    fun `sensor online follows its own timeout`() {
        val sensor = SensorResponse(id = "s", name = "Komora", object_id = "o", offline_timeout_seconds = 120)
        assertFalse(Formatters.isOnline(sensor, now))
        assertTrue(Formatters.isOnline(sensor.copy(last_message_at = "2026-10-05T11:58:30Z"), now))
        assertFalse(Formatters.isOnline(sensor.copy(last_message_at = "2026-10-05T11:57:00Z"), now))
    }

    @Test
    fun `alarm labels are Polish`() {
        assertEquals("Wysoka temperatura", Formatters.alarmType("high_temperature"))
        assertEquals("Wysoka temperatura", Formatters.alarmType("HIGH_TEMPERATURE"))
        assertEquals("Serwis w drodze", Formatters.alarmStatus("en_route"))
    }
}
