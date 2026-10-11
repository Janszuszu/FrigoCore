package pl.frigocore.service.ui.aggregates

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import pl.frigocore.service.data.model.AggregateResponse

class AggregateFormatTest {

    @Test
    fun `refrigerant charge in Polish notation without trailing zeros`() {
        assertEquals("4,2 kg", formatKilograms(4.2))
        assertEquals("6 kg", formatKilograms(6.0))
        assertEquals("0,25 kg", formatKilograms(0.25))
        assertEquals("5 kg", formatKilograms(4.999))
    }

    @Test
    fun `installation date as day month year`() {
        assertEquals("15.06.2021", formatDate("2021-06-15"))
        assertEquals("niedawno", formatDate("niedawno"))
    }

    @Test
    fun `backend aggregate parses with optional nameplate fields missing`() {
        val json = Json { ignoreUnknownKeys = true }
        val aggregate = json.decodeFromString<AggregateResponse>(
            """{"id":"a1","name":"Agregat","object_id":"o1","compressor_model":null,
               "sensor_ids":["s2","s1"],"display_order":0,"is_active":true,"created_at":"x"}""",
        )
        assertEquals(listOf("s2", "s1"), aggregate.sensor_ids)
        assertNull(aggregate.refrigerant_charge_kg)
    }
}
