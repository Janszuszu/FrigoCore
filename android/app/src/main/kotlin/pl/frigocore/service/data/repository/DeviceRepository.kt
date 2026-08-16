package pl.frigocore.service.data.repository

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import dagger.hilt.android.qualifiers.ApplicationContext
import pl.frigocore.service.data.api.FrigoCoreApi
import pl.frigocore.service.data.model.DeviceTokenRegister
import pl.frigocore.service.data.model.DeviceTokenResponse
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Registers/refreshes this device's FCM token against POST /devices/register
 * and de-registers it on logout. The locally-remembered device id lets
 * logout call DELETE /devices/{id} for exactly this device without the
 * backend having to expose a "delete by token" lookup.
 */
@Singleton
class DeviceRepository @Inject constructor(
    private val api: FrigoCoreApi,
    @ApplicationContext context: Context,
) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("frigocore_device", Context.MODE_PRIVATE)

    fun lastRegisteredToken(): String? = prefs.getString(KEY_LAST_TOKEN, null)
    private fun deviceId(): String? = prefs.getString(KEY_DEVICE_ID, null)

    suspend fun registerToken(fcmToken: String): ApiResult<DeviceTokenResponse> {
        val result = safeApiCall { api.registerDevice(DeviceTokenRegister(fcm_token = fcmToken, platform = "android")) }
        if (result is ApiResult.Success) {
            prefs.edit {
                putString(KEY_LAST_TOKEN, fcmToken)
                putString(KEY_DEVICE_ID, result.data.id)
            }
        }
        return result
    }

    /** Called on logout — best-effort; the local session clears regardless
     * of whether this succeeds (see AuthRepository.logout). */
    suspend fun unregisterCurrentDevice() {
        val id = deviceId() ?: return
        safeApiCallUnit { api.deleteDevice(id) }
        prefs.edit { remove(KEY_DEVICE_ID) }
    }

    private companion object {
        const val KEY_LAST_TOKEN = "last_fcm_token"
        const val KEY_DEVICE_ID = "device_id"
    }
}
