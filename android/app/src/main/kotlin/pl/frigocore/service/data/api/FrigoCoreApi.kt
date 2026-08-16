package pl.frigocore.service.data.api

import pl.frigocore.service.data.model.AlarmEventResponse
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.DeviceTokenRegister
import pl.frigocore.service.data.model.DeviceTokenResponse
import pl.frigocore.service.data.model.LoginRequest
import pl.frigocore.service.data.model.LoginResponse
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

    @GET("alarms/{alarmId}/events")
    suspend fun listAlarmEvents(@Path("alarmId") alarmId: String): Response<List<AlarmEventResponse>>

    @POST("devices/register")
    suspend fun registerDevice(@Body body: DeviceTokenRegister): Response<DeviceTokenResponse>

    @DELETE("devices/{deviceId}")
    suspend fun deleteDevice(@Path("deviceId") deviceId: String): Response<Unit>
}
