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

    fun temperature(value: Double?): String =
        if (value == null) "—" else String.format(Locale.forLanguageTag("pl"), "%.1f°C", value)

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

    /** Value without the unit, e.g. "-18,9" — the card renders "°C" smaller. */
    fun temperatureValue(value: Double?): String =
        if (value == null) "—" else String.format(Locale.forLanguageTag("pl"), "%.1f", value)

    fun alarmType(type: String): String = when (type.lowercase()) {
        AlarmType.HIGH_TEMPERATURE -> "Wysoka temperatura"
        AlarmType.LOW_TEMPERATURE -> "Niska temperatura"
        AlarmType.OFFLINE -> "Brak komunikacji"
        else -> type.ifBlank { "Alarm" }
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
