package pl.frigocore.service.data.api

import okhttp3.Interceptor
import okhttp3.Response
import pl.frigocore.service.data.local.SessionExpiredNotifier
import pl.frigocore.service.data.local.SessionStore
import javax.inject.Inject

/** Attaches the bearer token to every request and reports a 401 upstream —
 * matches app/api/deps.py:get_current_user, which is what returns 401 when
 * the token is missing/expired/invalid. */
class AuthInterceptor @Inject constructor(
    private val sessionStore: SessionStore,
    private val sessionExpiredNotifier: SessionExpiredNotifier,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val token = sessionStore.accessToken
        val request = if (token != null) {
            original.newBuilder().addHeader("Authorization", "Bearer $token").build()
        } else {
            original
        }
        val response = chain.proceed(request)
        if (response.code == 401 && token != null) {
            sessionExpiredNotifier.notifyExpired()
        }
        return response
    }
}
