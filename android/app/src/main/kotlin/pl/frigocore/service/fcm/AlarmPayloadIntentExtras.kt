package pl.frigocore.service.fcm

import android.content.Intent
import pl.frigocore.service.data.model.ServiceAlarmPayload

/**
 * Explicit per-field intent extras for [ServiceAlarmPayload] rather than a
 * Serializable/Parcelable blob — keeps the notification -> receiver ->
 * activity handoff simple to unit test without an Android runtime.
 */
private const val EXTRA_PREFIX = "pl.frigocore.service.extra."
private const val EXTRA_ALARM_ID = EXTRA_PREFIX + "ALARM_ID"
private const val EXTRA_ASSIGNMENT_ID = EXTRA_PREFIX + "ASSIGNMENT_ID"
private const val EXTRA_TIER = EXTRA_PREFIX + "TIER"
private const val EXTRA_SITE_ID = EXTRA_PREFIX + "SITE_ID"
private const val EXTRA_SITE_NAME = EXTRA_PREFIX + "SITE_NAME"
private const val EXTRA_ALARM_TYPE = EXTRA_PREFIX + "ALARM_TYPE"
private const val EXTRA_SEVERITY = EXTRA_PREFIX + "SEVERITY"
private const val EXTRA_TITLE = EXTRA_PREFIX + "TITLE"
private const val EXTRA_MESSAGE = EXTRA_PREFIX + "MESSAGE"
private const val EXTRA_SENSOR_NAME = EXTRA_PREFIX + "SENSOR_NAME"
private const val EXTRA_REQUIRES_ACTION = EXTRA_PREFIX + "REQUIRES_ACTION"
private const val EXTRA_CREATED_AT = EXTRA_PREFIX + "CREATED_AT"
private const val EXTRA_DISPATCHED_AT = EXTRA_PREFIX + "DISPATCHED_AT"
private const val EXTRA_VERSION = EXTRA_PREFIX + "VERSION"

fun Intent.putAlarmPayloadExtra(payload: ServiceAlarmPayload): Intent = apply {
    putExtra(EXTRA_ALARM_ID, payload.alarmId)
    putExtra(EXTRA_ASSIGNMENT_ID, payload.assignmentId)
    putExtra(EXTRA_TIER, payload.tier)
    putExtra(EXTRA_SITE_ID, payload.siteId)
    putExtra(EXTRA_SITE_NAME, payload.siteName)
    putExtra(EXTRA_ALARM_TYPE, payload.alarmType)
    putExtra(EXTRA_SEVERITY, payload.severity)
    putExtra(EXTRA_TITLE, payload.title)
    putExtra(EXTRA_MESSAGE, payload.message)
    putExtra(EXTRA_SENSOR_NAME, payload.sensorName)
    putExtra(EXTRA_REQUIRES_ACTION, payload.requiresAction)
    putExtra(EXTRA_CREATED_AT, payload.createdAt)
    putExtra(EXTRA_DISPATCHED_AT, payload.dispatchedAt)
    putExtra(EXTRA_VERSION, payload.version)
}

fun Intent.getAlarmPayloadExtra(): ServiceAlarmPayload? {
    val alarmId = getStringExtra(EXTRA_ALARM_ID) ?: return null
    val assignmentId = getStringExtra(EXTRA_ASSIGNMENT_ID) ?: return null
    val siteId = getStringExtra(EXTRA_SITE_ID) ?: return null
    return ServiceAlarmPayload(
        type = ServiceAlarmPayload.TYPE_SERVICE_ALARM,
        version = getIntExtra(EXTRA_VERSION, 1),
        alarmId = alarmId,
        assignmentId = assignmentId,
        tier = getIntExtra(EXTRA_TIER, 1),
        siteId = siteId,
        siteName = getStringExtra(EXTRA_SITE_NAME) ?: "",
        alarmType = getStringExtra(EXTRA_ALARM_TYPE) ?: "",
        severity = getStringExtra(EXTRA_SEVERITY) ?: "CRITICAL",
        title = getStringExtra(EXTRA_TITLE) ?: "",
        message = getStringExtra(EXTRA_MESSAGE) ?: "",
        sensorName = getStringExtra(EXTRA_SENSOR_NAME) ?: "",
        requiresAction = getBooleanExtra(EXTRA_REQUIRES_ACTION, false),
        createdAt = getStringExtra(EXTRA_CREATED_AT) ?: "",
        dispatchedAt = getStringExtra(EXTRA_DISPATCHED_AT) ?: "",
    )
}
