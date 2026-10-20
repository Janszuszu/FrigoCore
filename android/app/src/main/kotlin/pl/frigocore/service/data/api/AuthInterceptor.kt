package pl.frigocore.service.data.api

import kotlinx.serialization.json.Json
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import pl.frigocore.service.BuildConfig
import pl.frigocore.service.data.local.SessionExpiredNotifier
import pl.frigocore.service.data.local.SessionStore
import pl.frigocore.service.data.model.LoginResponse
import pl.frigocore.service.data.model.RefreshRequest
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/** Attaches the bearer token to every request. */
class AuthInterceptor @Inject constructor(
    private val sessionStore: SessionStore,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val token = sessionStore.accessToken ?: return chain.proceed(original)
        return chain.proceed(original.newBuilder().header("Authorization", "Bearer $token").build())
    }
}

/**
 * On a 401 (app/api/deps.py:get_current_user — token missing, expired or
 * invalid) trades the stored refresh token at auth/refresh for a new pair
 * and retries, so the phone stays signed in. Only when the backend refuses
 * the refresh token itself (expired, account deactivated, password changed)
 * is the session dropped and the user sent back to the login screen; a
 * network failure leaves the session alone.
 */
@Singleton
class TokenRefresher @Inject constructor(
    private val sessionStore: SessionStore,
    private val sessionExpiredNotifier: SessionExpiredNotifier,
    private val json: Json,
) : Authenticator {

    // Its own bare client: the refresh call must not go through this authenticator.
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()

    override fun authenticate(route: Route?, response: Response): Request? {
        val sent = response.request.header("Authorization")?.removePrefix("Bearer ") ?: return null
        // One retry only; a fresh token that still gets 401 is not a token problem.
        if (response.priorResponse != null) return null
        synchronized(this) {
            val current = sessionStore.accessToken ?: return null
            // Another request already refreshed while this one was in flight.
            if (current != sent) return response.request.withToken(current)
            val refreshToken = sessionStore.refreshToken
            if (refreshToken == null) {
                expire()
                return null
            }
            val pair = when (val result = refresh(refreshToken)) {
                is RefreshResult.Ok -> result.pair
                RefreshResult.Rejected -> {
                    expire()
                    return null
                }
                RefreshResult.Unreachable -> return null
            }
            sessionStore.save(pair.access_token, pair.refresh_token ?: refreshToken, pair.user)
            return response.request.withToken(pair.access_token)
        }
    }

    private sealed interface RefreshResult {
        data class Ok(val pair: LoginResponse) : RefreshResult
        data object Rejected : RefreshResult
        data object Unreachable : RefreshResult
    }

    private fun refresh(refreshToken: String): RefreshResult {
        val body = json.encodeToString(RefreshRequest.serializer(), RefreshRequest(refreshToken))
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder().url(BuildConfig.API_BASE_URL + "auth/refresh").post(body).build()
        return try {
            client.newCall(request).execute().use { resp ->
                when {
                    resp.isSuccessful -> RefreshResult.Ok(json.decodeFromString(LoginResponse.serializer(), resp.body!!.string()))
                    resp.code == 401 || resp.code == 403 -> RefreshResult.Rejected
                    else -> RefreshResult.Unreachable
                }
            }
        } catch (e: IOException) {
            RefreshResult.Unreachable
        } catch (e: IllegalArgumentException) {
            RefreshResult.Unreachable
        }
    }

    private fun expire() {
        sessionStore.clear()
        sessionExpiredNotifier.notifyExpired()
    }

    private fun Request.withToken(token: String): Request =
        newBuilder().header("Authorization", "Bearer $token").build()
}
