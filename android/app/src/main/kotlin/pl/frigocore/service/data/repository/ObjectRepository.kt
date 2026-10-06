package pl.frigocore.service.data.repository

import pl.frigocore.service.data.api.FrigoCoreApi
import pl.frigocore.service.data.model.MeasurementResponse
import pl.frigocore.service.data.model.ObjectResponse
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

    suspend fun getSensor(objectId: String, sensorId: String): ApiResult<SensorResponse> =
        safeApiCall { api.getSensor(objectId, sensorId) }

    /** Oldest-first readings from the last [hours], ready to plot. */
    suspend fun history(sensorId: String, hours: Long, targetPoints: Int = 120): ApiResult<List<MeasurementResponse>> {
        val since = Instant.now().minus(hours, ChronoUnit.HOURS).truncatedTo(ChronoUnit.SECONDS).toString()
        return when (val result = safeApiCall { api.listMeasurementsAggregated(sensorId, since, targetPoints) }) {
            is ApiResult.Success -> ApiResult.Success(result.data.reversed())
            is ApiResult.Error -> result
        }
    }
}
