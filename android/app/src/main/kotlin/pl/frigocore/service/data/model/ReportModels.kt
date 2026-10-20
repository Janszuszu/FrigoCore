package pl.frigocore.service.data.model

import kotlinx.serialization.Serializable

/** Mirrors backend/app/schemas.py ObjectDayReportResponse — the receivers'
 * analysed day, written every night after midnight. */
@Serializable
data class ObjectDayReportResponse(
    val day: String? = null,
    /** Days that have a report, newest first. */
    val days: List<String> = emptyList(),
    val receivers: List<ReceiverDayReportResponse> = emptyList(),
    val aggregates: List<AggregateDayReportResponse> = emptyList(),
)

/** An aggregate's day read from its power (or current) draw. */
@Serializable
data class AggregateDayReportResponse(
    val aggregate_id: String,
    val name: String,
    val day: String,
    /** "power" (W) or "current" (A). */
    val source: String = "power",
    val running_seconds: Long = 0,
    val idle_seconds: Long = 0,
    val starts: Int = 0,
    val avg_run_seconds: Long? = null,
    val max_run_seconds: Long? = null,
    val avg_idle_seconds: Long? = null,
    val duty_percent: Double? = null,
    val covered_seconds: Long = 0,
    val energy_kwh: Double? = null,
    val avg_running_value: Double? = null,
)

@Serializable
data class ReceiverDayReportResponse(
    val receiver_id: String,
    val name: String,
    val day: String,
    val cooling_count: Int = 0,
    val cooling_seconds: Long = 0,
    val idle_count: Int = 0,
    val idle_seconds: Long = 0,
    val duty_percent: Double? = null,
    val defrost_count: Int = 0,
    val covered_seconds: Long = 0,
    val min_temp: Double? = null,
    val avg_temp: Double? = null,
    val max_temp: Double? = null,
    val defrosts: List<DefrostEntry> = emptyList(),
    val off_periods: List<OffPeriodEntry> = emptyList(),
)

@Serializable
data class DefrostEntry(
    val start: String,
    val end: String,
    val peak: Double? = null,
    val recovery_seconds: Long? = null,
)

@Serializable
data class OffPeriodEntry(
    val start: String,
    val end: String,
    val peak: Double? = null,
)
