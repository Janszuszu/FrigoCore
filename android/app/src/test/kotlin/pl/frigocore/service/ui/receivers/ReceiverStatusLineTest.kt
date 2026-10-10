package pl.frigocore.service.ui.receivers

import org.junit.Assert.assertEquals
import org.junit.Test
import pl.frigocore.service.data.model.ReceiverResponse
import pl.frigocore.service.data.model.ReceiverState
import java.time.Instant

class ReceiverStatusLineTest {

    private val now = Instant.parse("2026-10-10T18:00:00Z")

    private fun receiver(
        state: String,
        since: String? = null,
        minutes: Double? = null,
        setpoint: Double? = null,
    ) = ReceiverResponse(
        id = "r1",
        name = "Mroźnia",
        object_id = "o1",
        state = state,
        state_since = since,
        minutes_to_setpoint = minutes,
        setpoint = setpoint,
    )

    @Test
    fun `cooling shows how long and the time left to setpoint`() {
        val line = receiverStatusLine(receiver(ReceiverState.COOLING, "2026-10-10T17:42:00Z", 12.4, -20.0), now)
        assertEquals("Chłodzenie od 18 min · pozostało ok. 12 min do -20,0°C", line)
    }

    @Test
    fun `long states read in hours and minutes`() {
        assertEquals("Postój od 1 h 30 min", receiverStatusLine(receiver(ReceiverState.IDLE, "2026-10-10T16:30:00Z"), now))
    }

    @Test
    fun `without a start time only the state is named`() {
        assertEquals("Odszranianie", receiverStatusLine(receiver(ReceiverState.DEFROST), now))
        assertEquals("Nieznany", receiverStatusLine(receiver("something-new"), now))
    }
}
