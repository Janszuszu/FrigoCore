package pl.frigocore.service.ui.sensor

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TemperatureChartTest {

    @Test
    fun `flat line still gets a visible whole-degree scale`() {
        val (lo, hi) = axisBounds(-18.0, -18.0)
        assertTrue(lo < -18.0 && hi > -18.0)
        assertEquals(lo, Math.floor(lo), 0.0)
        assertEquals(hi, Math.ceil(hi), 0.0)
    }

    @Test
    fun `bounds enclose the data with headroom`() {
        val (lo, hi) = axisBounds(2.3, 7.9)
        assertTrue(lo <= 2.3 - 0.5)
        assertTrue(hi >= 7.9 + 0.5)
    }
}
