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

/** Mirrors backend/app/schemas.py:ReceiverResponse — a refrigerated space
 * with its inferred working state. */
@Serializable
data class ReceiverResponse(
    val id: String,
    val name: String,
    val object_id: String,
    val chamber_sensor_id: String? = null,
    val evaporator_sensor_id: String? = null,
    val cut_in: Double? = null,
    val cut_out: Double? = null,
    val display_order: Int = 0,
    val is_active: Boolean = true,
    val chamber_temperature: Double? = null,
    val evaporator_temperature: Double? = null,
    val last_message_at: String? = null,
    /** cooling, idle, defrost or unknown (backend receiver_state.py). */
    val state: String = ReceiverState.UNKNOWN,
    val state_since: String? = null,
    /** While cooling: estimated minutes until the cut-out. */
    val minutes_to_cut_out: Double? = null,
    val chamber_rate: Double? = null,
    /** cooling or idle — which cycle stopwatch is running (defrost counts as idle). */
    val cycle_phase: String? = null,
    /** Cooling phase: running time, or the last complete one, as of the response. */
    val cooling_seconds: Long? = null,
    /** Idle phase: running time, or the last complete one, as of the response. */
    val idle_seconds: Long? = null,
)

object ReceiverState {
    const val COOLING = "cooling"
    const val IDLE = "idle"
    const val DEFROST = "defrost"
    const val UNKNOWN = "unknown"
}

/** Mirrors backend/app/schemas.py:AggregateResponse — a condensing unit's
 * nameplate data and the object's sensors shown with it, in order. */
@Serializable
data class AggregateResponse(
    val id: String,
    val name: String,
    val object_id: String,
    val compressor_model: String? = null,
    val refrigerant: String? = null,
    val refrigerant_charge_kg: Double? = null,
    /** ISO date, YYYY-MM-DD. */
    val installed_on: String? = null,
    /** Rated cooling capacity, kW. */
    val cooling_capacity_kw: Double? = null,
    val sensor_ids: List<String> = emptyList(),
    val display_order: Int = 0,
    val is_active: Boolean = true,
)
