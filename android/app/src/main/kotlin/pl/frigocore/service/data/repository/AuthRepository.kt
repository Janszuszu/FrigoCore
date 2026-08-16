package pl.frigocore.service.data.repository

import kotlinx.coroutines.flow.StateFlow
import pl.frigocore.service.data.api.FrigoCoreApi
import pl.frigocore.service.data.local.Session
import pl.frigocore.service.data.local.SessionStore
import pl.frigocore.service.data.model.LoginRequest
import pl.frigocore.service.data.model.UserResponse
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
    private val api: FrigoCoreApi,
    private val sessionStore: SessionStore,
    private val deviceRepository: DeviceRepository,
) {
    val session: StateFlow<Session?> = sessionStore.session
    val isLoggedIn: Boolean get() = sessionStore.accessToken != null
    val currentUser: UserResponse? get() = sessionStore.session.value?.user

    suspend fun login(username: String, password: String): ApiResult<UserResponse> {
        val result = safeApiCall { api.login(LoginRequest(username, password)) }
        return when (result) {
            is ApiResult.Success -> {
                sessionStore.save(result.data.access_token, result.data.user)
                ApiResult.Success(result.data.user)
            }
            is ApiResult.Error -> result
        }
    }

    /** Best-effort device de-registration, then always clears the local
     * session — a failed unregister call must not trap the technician in a
     * logged-in state they can no longer act from. */
    suspend fun logout() {
        deviceRepository.unregisterCurrentDevice()
        sessionStore.clear()
    }

    /** Called when the backend rejects the stored token (401) — the local
     * session is stale and must be dropped without attempting a graceful
     * device-unregister call that would just 401 again. */
    fun clearExpiredSession() {
        sessionStore.clear()
    }
}
