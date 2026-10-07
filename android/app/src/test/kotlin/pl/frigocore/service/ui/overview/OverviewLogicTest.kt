package pl.frigocore.service.ui.overview

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.AlarmStatus
import pl.frigocore.service.data.model.SensorResponse
import java.time.Instant

class OverviewLogicTest {

    private val now = Instant.parse("2026-10-07T08:00:00Z")

    private fun sensor(lastMessage: String? = "2026-10-07T07:59:30Z") = SensorResponse(
        id = "sensor-1",
        name = "Chłodnia",
        current_temperature = 4.2,
        last_message_at = lastMessage,
        offline_timeout_seconds = 120,
        object_id = "object-1",
    )

    private fun alarm(status: String, type: String = "high_temperature", sensorId: String = "sensor-1") = AlarmResponse(
        id = "alarm-$status-$type",
        alarm_type = type,
        status = status,
        detected_at = "2026-10-07T07:00:00Z",
        description = "",
        object_id = "object-1",
        sensor_id = sensorId,
        created_at = "2026-10-07T07:00:00Z",
        updated_at = "2026-10-07T07:00:00Z",
    )

    @Test
    fun `stats are min, mean and max of the 24h values`() {
        assertEquals(TempStats(2.0, 3.0, 4.0), tempStats(listOf(3.0, 2.0, 4.0)))
        assertNull(tempStats(emptyList()))
    }

    @Test
    fun `a fresh sensor without open alarms is OK`() {
        assertEquals(SensorStatus.OK, sensorStatus(sensor(), emptyList(), now))
    }

    @Test
    fun `an open temperature alarm on the sensor marks it ALARM`() {
        assertEquals(SensorStatus.ALARM, sensorStatus(sensor(), listOf(alarm(AlarmStatus.TRIGGERED)), now))
    }

    @Test
    fun `alarms on other sensors do not affect the card`() {
        assertEquals(SensorStatus.OK, sensorStatus(sensor(), listOf(alarm(AlarmStatus.TRIGGERED, sensorId = "other")), now))
    }

    @Test
    fun `a stale reading is OFFLINE`() {
        assertEquals(SensorStatus.OFFLINE, sensorStatus(sensor("2026-10-07T07:50:00Z"), emptyList(), now))
    }

    @Test
    fun `only triggered, acknowledged and en-route alarms count as open`() {
        assertEquals(true, isOpen(alarm(AlarmStatus.EN_ROUTE)))
        assertEquals(false, isOpen(alarm(AlarmStatus.RESOLVED)))
        assertEquals(false, isOpen(alarm(AlarmStatus.ARCHIVED)))
    }
}
