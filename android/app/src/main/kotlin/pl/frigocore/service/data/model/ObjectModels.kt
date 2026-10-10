package pl.frigocore.service.data.model

import kotlinx.serialization.Serializable

/** Mirrors backend/app/schemas.py:ObjectResponse. */
@Serializable
data class ObjectResponse(
    val id: String,
    val name: String,
    val description: String = "",
    val is_active: Boolean = true,
    val sensor_count: Int = 0,
    val online_sensor_count: Int = 0,
)

/** Mirrors backend/app/schemas.py:SensorResponse (fields the app reads). */
@Serializable
data class SensorResponse(
    val id: String,
    val name: String,
    val current_temperature: Double? = null,
    val last_message_at: String? = null,
    val offline_timeout_seconds: Int = 120,
    val is_active: Boolean = true,
    val icon: String = "thermometer",
    val display_order: Int = 0,
    val object_id: String,
    /** temperature, current, voltage, power or energy (backend sensor_kinds.py). */
    val kind: String = "temperature",
    /** Unit of current_temperature and of the sensor's measurements, e.g. "°C", "A". */
    val unit: String = "°C",
)

/** Mirrors backend/app/schemas.py:MeasurementResponse. */
@Serializable
data class MeasurementResponse(
    val id: String,
    val temperature: Double,
    val received_at: String,
    val sensor_id: String,
)
