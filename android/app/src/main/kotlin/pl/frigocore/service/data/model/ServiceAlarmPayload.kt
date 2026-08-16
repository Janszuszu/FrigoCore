package pl.frigocore.service.data.model

/**
 * Parsed shape of the SERVICE_ALARM FCM data payload built by
 * backend/app/services/notification_engine.py:build_service_alarm_payload.
 *
 * FCM data messages only carry string values (the server stringifies every
 * field — see firebase_client.send_to_token), so every value here arrives
 * as a raw string and is parsed defensively rather than assumed well-formed.
 */
data class ServiceAlarmPayload(
    val type: String,
    val version: Int,
    val alarmId: String,
    val assignmentId: String,
    val tier: Int,
    val siteId: String,
    val siteName: String,
    val alarmType: String,
    val severity: String,
    val title: String,
    val message: String,
    val requiresAction: Boolean,
    val createdAt: String,
) {
    companion object {
        const val TYPE_SERVICE_ALARM = "SERVICE_ALARM"

        /** Returns null if the payload isn't a well-formed SERVICE_ALARM
         * message — callers must not crash or half-render on a malformed
         * or future-shaped push. */
        fun fromDataMap(data: Map<String, String>): ServiceAlarmPayload? {
            if (data["type"] != TYPE_SERVICE_ALARM) return null
            val alarmId = data["alarm_id"] ?: return null
            val assignmentId = data["assignment_id"] ?: return null
            val siteId = data["site_id"] ?: return null

            return ServiceAlarmPayload(
                type = TYPE_SERVICE_ALARM,
                version = data["version"]?.toIntOrNull() ?: 1,
                alarmId = alarmId,
                assignmentId = assignmentId,
                tier = data["tier"]?.toIntOrNull() ?: 1,
                siteId = siteId,
                siteName = data["site_name"] ?: "",
                alarmType = data["alarm_type"] ?: "",
                severity = data["severity"] ?: "CRITICAL",
                title = data["title"] ?: "ALARM KRYTYCZNY",
                message = data["message"] ?: "",
                // Python's str(True) serializes as "True", not "true" — this
                // must match that exact wire format, not JSON boolean rules.
                requiresAction = data["requires_action"]?.equals("true", ignoreCase = true) ?: false,
                createdAt = data["created_at"] ?: "",
            )
        }
    }
}
