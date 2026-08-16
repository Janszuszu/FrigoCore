package pl.frigocore.service.data.repository

import pl.frigocore.service.data.api.FrigoCoreApi
import pl.frigocore.service.data.model.AlarmEventResponse
import pl.frigocore.service.data.model.AlarmResponse
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AlarmRepository @Inject constructor(
    private val api: FrigoCoreApi,
) {
    suspend fun listAlarms(status: String? = null): ApiResult<List<AlarmResponse>> =
        safeApiCall { api.listAlarms(status = status) }

    suspend fun getAlarm(alarmId: String): ApiResult<AlarmResponse> =
        safeApiCall { api.getAlarm(alarmId) }

    /** Only ever returns Success once /accept has actually been confirmed
     * by the backend — see ApiResult's contract note. */
    suspend fun acceptAlarm(alarmId: String): ApiResult<AlarmResponse> =
        safeApiCall { api.acceptAlarm(alarmId) }

    suspend fun declineAlarm(alarmId: String): ApiResult<AlarmResponse> =
        safeApiCall { api.declineAlarm(alarmId) }

    suspend fun markEnRoute(alarmId: String): ApiResult<AlarmResponse> =
        safeApiCall { api.alarmEnRoute(alarmId) }

    suspend fun resolveAlarm(alarmId: String): ApiResult<AlarmResponse> =
        safeApiCall { api.resolveAlarm(alarmId) }

    suspend fun listEvents(alarmId: String): ApiResult<List<AlarmEventResponse>> =
        safeApiCall { api.listAlarmEvents(alarmId) }
}
