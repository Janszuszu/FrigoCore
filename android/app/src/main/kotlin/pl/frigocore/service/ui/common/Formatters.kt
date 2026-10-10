package pl.frigocore.service.ui.common

import pl.frigocore.service.data.model.AlarmStatus
import pl.frigocore.service.data.model.AlarmType
import pl.frigocore.service.data.model.SensorResponse
import java.time.Duration
import java.time.Instant
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Pure display helpers — no Android dependencies so they unit-test on the JVM. */
object Formatters {

    private val timeFormat = DateTimeFormatter.ofPattern("HH:mm", Locale.forLanguageTag("pl"))
    private val dateTimeFormat = DateTimeFormatter.ofPattern("dd.MM HH:mm", Locale.forLanguageTag("pl"))
    private val shortDateFormat = DateTimeFormatter.ofPattern("dd.MM", Locale.forLanguageTag("pl"))

    /** Backend timestamps carry an offset on Postgres but are naive UTC on
     * SQLite; both are accepted, anything else yields null. */
    fun parseInstant(raw: String?): Instant? {
        if (raw.isNullOrBlank()) return null
        return runCatching { OffsetDateTime.parse(raw).toInstant() }.getOrNull()
            ?: runCatching { LocalDateTime.parse(raw).toInstant(ZoneOffset.UTC) }.getOrNull()
    }

    fun dateTime(raw: String?, zone: ZoneId = ZoneId.systemDefault()): String =
        parseInstant(raw)?.atZone(zone)?.format(dateTimeFormat) ?: "—"

    fun time(instant: Instant, zone: ZoneId = ZoneId.systemDefault()): String =
        instant.atZone(zone).format(timeFormat)

    fun shortDate(instant: Instant, zone: ZoneId = ZoneId.systemDefault()): String =
        instant.atZone(zone).format(shortDateFormat)

    private val decimals = mapOf("°C" to 1, "A" to 2, "V" to 1, "W" to 0, "kWh" to 2)

    /** Value without the unit, rounded for it — e.g. "-18,9", "0,35", "241,3". */
    fun readingValue(value: Double?, unit: String): String =
        if (value == null) "—"
        else String.format(Locale.forLanguageTag("pl"), "%.${decimals[unit] ?: 1}f", value)

    /** Value with its unit — "-18,9°C" (degrees attach), "241,3 V". */
    fun reading(value: Double?, unit: String): String {
        val number = readingValue(value, unit)
        return when {
            value == null -> number
            unit == "°C" -> "$number°C"
            else -> "$number $unit"
        }
    }

    fun temperature(value: Double?): String = reading(value, "°C")

    /** "przed chwilą", "5 min temu", "3 godz. temu", "2 dni temu". */
    fun ago(raw: String?, now: Instant = Instant.now()): String {
        val instant = parseInstant(raw) ?: return "brak danych"
        val seconds = Duration.between(instant, now).seconds.coerceAtLeast(0)
        return when {
            seconds < 60 -> "przed chwilą"
            seconds < 3600 -> "${seconds / 60} min temu"
            seconds < 86_400 -> "${seconds / 3600} godz. temu"
            else -> "${seconds / 86_400} dni temu"
        }
    }

    /** Same rule as backend routes.py:_sensor_is_online. */
    fun isOnline(sensor: SensorResponse, now: Instant = Instant.now()): Boolean {
        val last = parseInstant(sensor.last_message_at) ?: return false
        return Duration.between(last, now).seconds <= sensor.offline_timeout_seconds
    }

    /** Alarm cause worded for what the sensor measures (backend sensor_kinds.py). */
    fun alarmType(type: String, kind: String = "temperature"): String {
        val high = when (type.lowercase()) {
            AlarmType.HIGH_TEMPERATURE -> true
            AlarmType.LOW_TEMPERATURE -> false
            AlarmType.OFFLINE -> return "Brak komunikacji"
            else -> return type.ifBlank { "Alarm" }
        }
        return when (kind) {
            "current" -> if (high) "Przeciążenie — wysoki prąd" else "Niski prąd"
            "voltage" -> if (high) "Wysokie napięcie" else "Niskie napięcie"
            "power" -> if (high) "Wysoka moc" else "Niska moc"
            "energy" -> if (high) "Wysokie zużycie energii" else "Niskie zużycie energii"
            else -> if (high) "Wysoka temperatura" else "Niska temperatura"
        }
    }

    fun alarmStatus(status: String): String = when (status) {
        AlarmStatus.PENDING -> "Oczekuje"
        AlarmStatus.TRIGGERED -> "Aktywny"
        AlarmStatus.ACKNOWLEDGED -> "Przyjęty"
        AlarmStatus.EN_ROUTE -> "Serwis w drodze"
        AlarmStatus.RESOLVED -> "Zakończony"
        AlarmStatus.ARCHIVED -> "Zarchiwizowany"
        else -> status
    }
}
