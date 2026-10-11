package pl.frigocore.service.ui.aggregates

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import pl.frigocore.service.data.model.AggregateResponse

class AggregateFormatTest {

    @Test
    fun `amounts in Polish notation without trailing zeros`() {
        assertEquals("4,2 kg", formatAmount(4.2, "kg"))
        assertEquals("6 kW", formatAmount(6.0, "kW"))
        assertEquals("0,25 kg", formatAmount(0.25, "kg"))
        assertEquals("5 kg", formatAmount(4.999, "kg"))
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
            """{"id":"a1","name":"Agregat","object_id":"o1","compressor_model":null,"cooling_capacity_kw":5.8,
               "sensor_ids":["s2","s1"],"display_order":0,"is_active":true,"created_at":"x"}""",
        )
        assertEquals(listOf("s2", "s1"), aggregate.sensor_ids)
        assertNull(aggregate.refrigerant_charge_kg)
        assertEquals(5.8, aggregate.cooling_capacity_kw!!, 0.0)
    }
}
