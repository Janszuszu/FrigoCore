package pl.frigocore.service.data.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/** Mirrors backend/app/schemas.py:AlarmResponse exactly — do not add fields
 * the API doesn't send; do not rename to a different wire shape. */
@Serializable
data class AlarmResponse(
    val id: String,
    val alarm_type: String,
    val status: String,
    val trigger_value: Double? = null,
    val detected_at: String,
    val triggered_at: String? = null,
    val acknowledged_at: String? = null,
    val en_route_at: String? = null,
    val resolved_at: String? = null,
    val description: String,
    val object_id: String,
    val sensor_id: String? = null,
    val created_at: String,
    val updated_at: String,
)

object AlarmStatus {
    const val PENDING = "pending"
    const val TRIGGERED = "triggered"
    const val ACKNOWLEDGED = "acknowledged"
    const val EN_ROUTE = "en_route"
    const val RESOLVED = "resolved"
    const val ARCHIVED = "archived"
}

object AlarmType {
    const val HIGH_TEMPERATURE = "high_temperature"
    const val LOW_TEMPERATURE = "low_temperature"
    const val OFFLINE = "offline"
}

@Serializable
data class AlarmEventResponse(
    val id: String,
    val alarm_id: String,
    val event_type: String,
    val actor_user_id: String? = null,
    val message: String? = null,
    val event_metadata: Map<String, JsonElement>? = null,
    val created_at: String,
)

@Serializable
data class AlarmAssignmentResponse(
    val id: String,
    val alarm_id: String,
    val tier: Int,
    val target_user_id: String? = null,
    val target_role: String? = null,
    val outcome: String,
    val dispatched_at: String,
    val delivered_at: String? = null,
    val responded_at: String? = null,
    val expires_at: String? = null,
    val created_at: String,
)
