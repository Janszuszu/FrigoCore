package pl.frigocore.service.data.repository

import pl.frigocore.service.data.api.FrigoCoreApi
import pl.frigocore.service.data.model.AggregateResponse
import pl.frigocore.service.data.model.AlarmLimitsResponse
import pl.frigocore.service.data.model.MeasurementResponse
import pl.frigocore.service.data.model.MeterResponse
import pl.frigocore.service.data.model.MeterTotalResponse
import pl.frigocore.service.data.model.ObjectResponse
import pl.frigocore.service.data.model.ReceiverResponse
import pl.frigocore.service.data.model.SensorResponse
import java.time.Instant
import java.time.temporal.ChronoUnit
import javax.inject.Inject
import javax.inject.Singleton

/** Read-only access to objects, sensors and their history. The backend
 * scopes every call to what the logged-in user may see — an owner only
 * gets their own objects, a technician gets all of them. */
@Singleton
class ObjectRepository @Inject constructor(
    private val api: FrigoCoreApi,
) {
    suspend fun listObjects(): ApiResult<List<ObjectResponse>> =
        safeApiCall { api.listObjects() }

    suspend fun getObject(objectId: String): ApiResult<ObjectResponse> =
        safeApiCall { api.getObject(objectId) }

    suspend fun listSensors(objectId: String): ApiResult<List<SensorResponse>> =
        safeApiCall { api.listSensors(objectId) }

    suspend fun listReceivers(objectId: String): ApiResult<List<ReceiverResponse>> =
        safeApiCall { api.listReceivers(objectId) }

    suspend fun listAggregates(objectId: String): ApiResult<List<AggregateResponse>> =
        safeApiCall { api.listAggregates(objectId) }

    suspend fun listMeters(objectId: String): ApiResult<List<MeterResponse>> =
        safeApiCall { api.listMeters(objectId) }

    suspend fun metersTotal(objectId: String): ApiResult<MeterTotalResponse> =
        safeApiCall { api.metersTotal(objectId) }

    suspend fun getSensor(objectId: String, sensorId: String): ApiResult<SensorResponse> =
        safeApiCall { api.getSensor(objectId, sensorId) }

    /** Oldest-first readings from the last [hours], ready to plot. */
    suspend fun history(sensorId: String, hours: Long, targetPoints: Int = 120): ApiResult<List<MeasurementResponse>> {
        val since = Instant.now().minus(hours, ChronoUnit.HOURS)
        return history(sensorId, since, until = null, targetPoints)
    }

    /** Oldest-first readings in [since, until] (until = now when null). */
    suspend fun history(sensorId: String, since: Instant, until: Instant?, targetPoints: Int = 120): ApiResult<List<MeasurementResponse>> {
        val sinceParam = since.truncatedTo(ChronoUnit.SECONDS).toString()
        val untilParam = until?.truncatedTo(ChronoUnit.SECONDS)?.toString()
        return when (val result = safeApiCall { api.listMeasurementsAggregated(sensorId, sinceParam, targetPoints, untilParam) }) {
            is ApiResult.Success -> ApiResult.Success(result.data.reversed())
            is ApiResult.Error -> result
        }
    }

    suspend fun alarmLimits(sensorId: String): ApiResult<AlarmLimitsResponse> =
        safeApiCall { api.alarmLimits(sensorId) }
}
