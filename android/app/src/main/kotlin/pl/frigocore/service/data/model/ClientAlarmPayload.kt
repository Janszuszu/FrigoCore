package pl.frigocore.service.data.model

/**
 * Parsed CLIENT_ALARM FCM data payload built by
 * backend/app/services/notification_engine.py:build_client_alarm_payload —
 * an informational notice to an object owner (alarm raised, service en
 * route, alarm closed). Never drives the critical full-screen alarm UI.
 */
data class ClientAlarmPayload(
    val event: String,
    val alarmId: String,
    val siteId: String,
    val siteName: String,
    val alarmType: String,
    val title: String,
    val message: String,
    val sensorName: String,
    val createdAt: String,
) {
    /** Seeds AlarmActivity, which then loads the authoritative alarm. */
    fun toServiceAlarmPayload(): ServiceAlarmPayload = ServiceAlarmPayload(
        type = TYPE_CLIENT_ALARM,
        version = 1,
        alarmId = alarmId,
        assignmentId = "",
        tier = 0,
        siteId = siteId,
        siteName = siteName,
        alarmType = alarmType,
        severity = "",
        title = title,
        message = message,
        sensorName = sensorName,
        requiresAction = false,
        createdAt = createdAt,
        dispatchedAt = "",
    )

    companion object {
        const val TYPE_CLIENT_ALARM = "CLIENT_ALARM"
        const val EVENT_TRIGGERED = "triggered"
        const val EVENT_EN_ROUTE = "en_route"
        const val EVENT_RESOLVED = "resolved"

        fun fromDataMap(data: Map<String, String>): ClientAlarmPayload? {
            if (data["type"] != TYPE_CLIENT_ALARM) return null
            val alarmId = data["alarm_id"] ?: return null
            return ClientAlarmPayload(
                event = data["event"] ?: EVENT_TRIGGERED,
                alarmId = alarmId,
                siteId = data["site_id"] ?: "",
                siteName = data["site_name"] ?: "",
                alarmType = data["alarm_type"] ?: "",
                title = data["title"] ?: "Alarm",
                message = data["message"] ?: "",
                sensorName = data["sensor_name"] ?: "",
                createdAt = data["created_at"] ?: "",
            )
        }
    }
}
