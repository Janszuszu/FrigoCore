package pl.frigocore.service.ui.aggregates

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import pl.frigocore.service.data.model.SensorResponse

class CycleSensorsTest {

    private fun sensor(name: String, kind: String = "temperature") =
        SensorResponse(id = name, name = name, object_id = "o", kind = kind)

    @Test
    fun `Lewiatan aggregate gets the diagram with every role`() {
        val cycle = cycleSensors(
            listOf(
                sensor("Temperatura zewnętrzna"),
                sensor("Agregat — tłoczenie"),
                sensor("Agregat — skraplacz"),
                sensor("Agregat — sprężarka"),
                sensor("Agregat — ssanie"),
                sensor("Agregat — moc", "power"),
                sensor("Agregat — prąd", "current"),
            ),
        )
        assertNotNull(cycle)
        assertEquals("Agregat — tłoczenie", cycle!!.discharge.name)
        assertEquals("Agregat — ssanie", cycle.suction.name)
        assertEquals("Agregat — skraplacz", cycle.condenser.name)
        assertEquals("Agregat — sprężarka", cycle.compressor?.name)
        assertEquals("Temperatura zewnętrzna", cycle.outdoor?.name)
        assertEquals("Agregat — prąd", cycle.current?.name)
        assertEquals("Agregat — moc", cycle.power?.name)
    }

    @Test
    fun `Biskupiec aggregate without condenser and meter gets only the rows`() {
        assertNull(cycleSensors(listOf(sensor("Zewnetrzna"), sensor("Chłodnia/Pchanie"), sensor("Chłodnia/Ssanie"))))
    }

    @Test
    fun `no meter, no diagram`() {
        assertNull(cycleSensors(listOf(sensor("Tłoczenie"), sensor("Ssanie"), sensor("Skraplacz"))))
    }
}

class AirArrowGlowTest {
    @Test
    fun `the light runs down the three arrows and wraps round`() {
        org.junit.Assert.assertEquals(1f, arrowGlow(0, 0f), 1e-6f)
        org.junit.Assert.assertEquals(0f, arrowGlow(1, 0f), 1e-6f)
        org.junit.Assert.assertEquals(0.5f, arrowGlow(1, 0.5f), 1e-6f)
        org.junit.Assert.assertEquals(1f, arrowGlow(2, 2f), 1e-6f)
        // Just before it wraps the top arrow starts lighting again.
        org.junit.Assert.assertEquals(0.5f, arrowGlow(0, 2.5f), 1e-6f)
    }
}
