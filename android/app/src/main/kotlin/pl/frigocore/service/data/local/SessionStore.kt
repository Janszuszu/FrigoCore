package pl.frigocore.service.data.local

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json
import pl.frigocore.service.data.model.UserResponse
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Holds the access token and current user, backed by
 * EncryptedSharedPreferences (AES-256-GCM, Android Keystore-wrapped key) —
 * the platform-recommended secure storage for a single bearer token, rather
 * than a second, home-grown auth/credential system.
 */
@Singleton
class SessionStore @Inject constructor(@ApplicationContext context: Context) {

    private val prefs: SharedPreferences by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "frigocore_secure_session",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    private val _session = MutableStateFlow(loadSession())
    val session: StateFlow<Session?> = _session.asStateFlow()

    val accessToken: String?
        get() = _session.value?.accessToken

    fun save(accessToken: String, user: UserResponse) {
        val userJson = Json.encodeToString(UserResponse.serializer(), user)
        prefs.edit()
            .putString(KEY_TOKEN, accessToken)
            .putString(KEY_USER, userJson)
            .apply()
        _session.value = Session(accessToken, user)
    }

    fun clear() {
        prefs.edit().remove(KEY_TOKEN).remove(KEY_USER).apply()
        _session.value = null
    }

    private fun loadSession(): Session? {
        val token = prefs.getString(KEY_TOKEN, null) ?: return null
        val userJson = prefs.getString(KEY_USER, null) ?: return null
        val user = runCatching { Json.decodeFromString(UserResponse.serializer(), userJson) }.getOrNull()
            ?: return null
        return Session(token, user)
    }

    private companion object {
        const val KEY_TOKEN = "access_token"
        const val KEY_USER = "user"
    }
}

data class Session(val accessToken: String, val user: UserResponse)
