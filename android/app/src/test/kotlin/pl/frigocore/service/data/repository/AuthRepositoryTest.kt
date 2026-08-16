package pl.frigocore.service.data.repository

import com.google.common.truth.Truth.assertThat
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Before
import org.junit.Test
import pl.frigocore.service.data.api.FrigoCoreApi
import pl.frigocore.service.data.local.SessionStore
import pl.frigocore.service.data.model.LoginResponse
import pl.frigocore.service.data.model.UserResponse
import retrofit2.Response

/** Matches backend/app/api/routes.py:login — 401 on bad credentials or an
 * inactive/unknown user (app/core/security.py:verify_password). */
class AuthRepositoryTest {

    private lateinit var api: FrigoCoreApi
    private lateinit var sessionStore: SessionStore
    private lateinit var deviceRepository: DeviceRepository
    private lateinit var repository: AuthRepository

    @Before
    fun setUp() {
        api = mockk()
        sessionStore = mockk(relaxed = true)
        deviceRepository = mockk(relaxed = true)
        every { sessionStore.session } returns MutableStateFlow(null)
        repository = AuthRepository(api, sessionStore, deviceRepository)
    }

    private fun user() = UserResponse(
        id = "user-1",
        username = "tech1",
        email = "tech1@frigocore.pl",
        full_name = "Technik Jeden",
        role = "serwisant",
        is_active = true,
        object_ids = emptyList(),
    )

    @Test
    fun `successful login saves the session`() = runTest {
        coEvery { api.login(any()) } returns Response.success(
            LoginResponse(access_token = "token-abc", user = user()),
        )

        val result = repository.login("tech1", "correct-password")

        assertThat(result).isInstanceOf(ApiResult.Success::class.java)
        verify { sessionStore.save("token-abc", user()) }
    }

    @Test
    fun `invalid credentials surface a 401 auth failure, never a saved session`() = runTest {
        coEvery { api.login(any()) } returns Response.error(
            401,
            "{\"detail\":\"Nieprawidłowa nazwa użytkownika lub hasło\"}"
                .toResponseBody("application/json".toMediaType()),
        )

        val result = repository.login("tech1", "wrong-password")

        assertThat(result).isInstanceOf(ApiResult.Error::class.java)
        assertThat((result as ApiResult.Error).httpCode).isEqualTo(401)
        verify(exactly = 0) { sessionStore.save(any(), any()) }
    }

    @Test
    fun `network failure during login surfaces as Error without saving a session`() = runTest {
        coEvery { api.login(any()) } throws java.io.IOException("no connectivity")

        val result = repository.login("tech1", "correct-password")

        assertThat(result).isInstanceOf(ApiResult.Error::class.java)
        verify(exactly = 0) { sessionStore.save(any(), any()) }
    }

    @Test
    fun `logout unregisters the device then always clears the session`() = runTest {
        repository.logout()

        coVerify { deviceRepository.unregisterCurrentDevice() }
        verify { sessionStore.clear() }
    }

    @Test
    fun `an expired session (401 on any call) clears the local session without a device unregister call`() = runTest {
        repository.clearExpiredSession()

        verify { sessionStore.clear() }
        coVerify(exactly = 0) { deviceRepository.unregisterCurrentDevice() }
    }
}
