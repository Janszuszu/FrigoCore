package pl.frigocore.service.ui.meters

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import pl.frigocore.service.data.model.Consumption
import pl.frigocore.service.data.model.EnergyDay
import java.time.LocalDate

class MeterBarsTest {

    // Wednesday 1 October 2026: the week began on Monday 29 September.
    private val today = LocalDate.of(2026, 10, 1)
    private val used = Consumption(
        days = listOf(EnergyDay("2026-09-29", 3.5), EnergyDay("2026-10-01", 1.25)),
    )

    @Test
    fun `week runs Monday to Sunday across the month boundary`() {
        val bars = weekBars(used, today)
        assertEquals(7, bars.size)
        assertEquals(LocalDate.of(2026, 9, 28), bars.first().day)
        assertEquals(LocalDate.of(2026, 10, 4), bars.last().day)
        assertEquals(3.5, bars[1].kwh!!, 0.0)
        assertNull(bars[2].kwh) // no readings that day
        assertEquals(1.25, bars[3].kwh!!, 0.0)
    }

    @Test
    fun `month has a bar for every day`() {
        val bars = monthBars(used, today)
        assertEquals(31, bars.size)
        assertEquals(1.25, bars.first().kwh!!, 0.0)
        assertNull(bars.last().kwh)
    }

    @Test
    fun `consumption with one decimal`() {
        assertEquals("4,2 kWh", kwh(4.24))
        assertEquals("—", kwh(null))
    }
}
