package pl.frigocore.service.data.repository

import androidx.test.core.app.ApplicationProvider
import com.google.common.truth.Truth.assertThat
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import pl.frigocore.service.data.api.FrigoCoreApi
import pl.frigocore.service.data.model.DeviceTokenResponse
import retrofit2.Response

/** FCM token registration and refresh — POST /devices/register, matching
 * backend/app/api/routes.py:register_device, which re-claims an existing
 * token row rather than erroring on re-registration. */
@RunWith(RobolectricTestRunner::class)
class DeviceRepositoryTest {

    private lateinit var api: FrigoCoreApi
    private lateinit var repository: DeviceRepository

    @Before
    fun setUp() {
        api = mockk()
        val context = ApplicationProvider.getApplicationContext<android.app.Application>()
        repository = DeviceRepository(api, context)
    }

    private fun deviceResponse(id: String = "device-1") = DeviceTokenResponse(
        id = id,
        user_id = "user-1",
        platform = "android",
        is_active = true,
        last_seen_at = "2026-08-16T10:00:00Z",
        created_at = "2026-08-16T10:00:00Z",
        updated_at = "2026-08-16T10:00:00Z",
    )

    @Test
    fun `registers a new FCM token successfully`() = runTest {
        coEvery { api.registerDevice(any()) } returns Response.success(deviceResponse())

        val result = repository.registerToken("fcm-token-1")

        assertThat(result).isInstanceOf(ApiResult.Success::class.java)
        assertThat(repository.lastRegisteredToken()).isEqualTo("fcm-token-1")
    }

    @Test
    fun `token refresh re-registers with the same device flow as initial registration`() = runTest {
        coEvery { api.registerDevice(any()) } returns Response.success(deviceResponse("device-1"))
        repository.registerToken("old-token")

        coEvery { api.registerDevice(any()) } returns Response.success(deviceResponse("device-1"))
        val refreshed = repository.registerToken("new-token")

        assertThat(refreshed).isInstanceOf(ApiResult.Success::class.java)
        assertThat(repository.lastRegisteredToken()).isEqualTo("new-token")
    }

    @Test
    fun `registration failure surfaces as ApiResult Error, not a crash`() = runTest {
        coEvery { api.registerDevice(any()) } returns Response.error(
            401, "{\"detail\":\"Not authenticated\"}".toResponseBody("application/json".toMediaType()),
        )

        val result = repository.registerToken("fcm-token-1")

        assertThat(result).isInstanceOf(ApiResult.Error::class.java)
        assertThat((result as ApiResult.Error).httpCode).isEqualTo(401)
    }

    @Test
    fun `network failure during registration surfaces as ApiResult Error`() = runTest {
        coEvery { api.registerDevice(any()) } throws java.io.IOException("no connectivity")

        val result = repository.registerToken("fcm-token-1")

        assertThat(result).isInstanceOf(ApiResult.Error::class.java)
    }
}
