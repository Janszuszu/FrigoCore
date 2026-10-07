package pl.frigocore.service.data.api

import pl.frigocore.service.data.model.AlarmEventResponse
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.ArchiveResolvedResponse
import pl.frigocore.service.data.model.DeviceTokenRegister
import pl.frigocore.service.data.model.DeviceTokenResponse
import pl.frigocore.service.data.model.LoginRequest
import pl.frigocore.service.data.model.LoginResponse
import pl.frigocore.service.data.model.MeasurementResponse
import pl.frigocore.service.data.model.ObjectResponse
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.data.model.UserResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.POST
import retrofit2.http.Query

/**
 * Thin mirror of backend/app/api/routes.py. Every path, verb and payload
 * shape here must match the existing FastAPI contract exactly — this
 * client does not invent endpoints.
 */
interface FrigoCoreApi {

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): Response<LoginResponse>

    @GET("auth/me")
    suspend fun me(): Response<UserResponse>

    @GET("objects")
    suspend fun listObjects(): Response<List<ObjectResponse>>

    @GET("objects/{objectId}")
    suspend fun getObject(@Path("objectId") objectId: String): Response<ObjectResponse>

    @GET("objects/{objectId}/sensors")
    suspend fun listSensors(@Path("objectId") objectId: String): Response<List<SensorResponse>>

    @GET("objects/{objectId}/sensors/{sensorId}")
    suspend fun getSensor(
        @Path("objectId") objectId: String,
        @Path("sensorId") sensorId: String,
    ): Response<SensorResponse>

    /** Newest-first, decimated server-side to ~target_points (min/max per bucket). */
    @GET("sensors/{sensorId}/measurements/aggregated")
    suspend fun listMeasurementsAggregated(
        @Path("sensorId") sensorId: String,
        @Query("since") since: String,
        @Query("target_points") targetPoints: Int = 120,
    ): Response<List<MeasurementResponse>>

    @GET("alarms")
    suspend fun listAlarms(
        @Query("object_id") objectId: String? = null,
        @Query("status") status: String? = null,
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 100,
    ): Response<List<AlarmResponse>>

    @GET("alarms/{alarmId}")
    suspend fun getAlarm(@Path("alarmId") alarmId: String): Response<AlarmResponse>

    @POST("alarms/{alarmId}/accept")
    suspend fun acceptAlarm(@Path("alarmId") alarmId: String): Response<AlarmResponse>

    @POST("alarms/{alarmId}/decline")
    suspend fun declineAlarm(@Path("alarmId") alarmId: String): Response<AlarmResponse>

    @POST("alarms/{alarmId}/en-route")
    suspend fun alarmEnRoute(@Path("alarmId") alarmId: String): Response<AlarmResponse>

    @POST("alarms/{alarmId}/resolve")
    suspend fun resolveAlarm(@Path("alarmId") alarmId: String): Response<AlarmResponse>

    /** Service staff only: archives every RESOLVED alarm ("clear history"). */
    @POST("alarms/archive-resolved")
    suspend fun archiveResolvedAlarms(): Response<ArchiveResolvedResponse>

    @GET("alarms/{alarmId}/events")
    suspend fun listAlarmEvents(@Path("alarmId") alarmId: String): Response<List<AlarmEventResponse>>

    @POST("devices/register")
    suspend fun registerDevice(@Body body: DeviceTokenRegister): Response<DeviceTokenResponse>

    @DELETE("devices/{deviceId}")
    suspend fun deleteDevice(@Path("deviceId") deviceId: String): Response<Unit>
}
