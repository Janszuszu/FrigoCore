package pl.frigocore.service.ui.objects

import org.junit.Assert.assertEquals
import org.junit.Test
import pl.frigocore.service.data.model.AlarmResponse

class ObjectsViewModelTest {

    private fun alarm(objectId: String, status: String) = AlarmResponse(
        id = "$objectId-$status-${Math.random()}",
        alarm_type = "high_temperature",
        status = status,
        detected_at = "2026-10-05T10:00:00Z",
        description = "",
        object_id = objectId,
        created_at = "2026-10-05T10:00:00Z",
        updated_at = "2026-10-05T10:00:00Z",
    )

    @Test
    fun `only open alarms are counted per object`() {
        val counts = openAlarmCounts(
            listOf(
                alarm("a", "triggered"),
                alarm("a", "en_route"),
                alarm("a", "resolved"),
                alarm("b", "acknowledged"),
                alarm("c", "pending"),
                alarm("c", "archived"),
            ),
        )
        assertEquals(mapOf("a" to 2, "b" to 1), counts)
    }
}
