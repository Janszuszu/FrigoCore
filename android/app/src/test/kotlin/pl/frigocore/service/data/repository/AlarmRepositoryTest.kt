package pl.frigocore.service.data.repository

import com.google.common.truth.Truth.assertThat
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Before
import org.junit.Test
import pl.frigocore.service.data.api.FrigoCoreApi
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.AlarmStatus
import retrofit2.Response
import java.io.IOException

/** Accept/decline/en-route/resolve — mirrors the state-machine endpoints in
 * backend/app/api/routes.py exactly (POST /alarms/{id}/accept|decline|en-route|resolve). */
class AlarmRepositoryTest {

    private lateinit var api: FrigoCoreApi
    private lateinit var repository: AlarmRepository

    @Before
    fun setUp() {
        api = mockk()
        repository = AlarmRepository(api)
    }

    private fun alarm(status: String) = AlarmResponse(
        id = "alarm-1",
        alarm_type = "high_temperature",
        status = status,
        trigger_value = 9.5,
        detected_at = "2026-08-16T10:00:00Z",
        triggered_at = "2026-08-16T10:00:00Z",
        description = "Temperatura przekroczona",
        object_id = "object-1",
        sensor_id = "sensor-1",
        created_at = "2026-08-16T10:00:00Z",
        updated_at = "2026-08-16T10:00:00Z",
    )

    @Test
    fun `accept returns the confirmed ACKNOWLEDGED alarm`() = runTest {
        coEvery { api.acceptAlarm("alarm-1") } returns Response.success(alarm(AlarmStatus.ACKNOWLEDGED))

        val result = repository.acceptAlarm("alarm-1")

        assertThat(result).isInstanceOf(ApiResult.Success::class.java)
        assertThat((result as ApiResult.Success).data.status).isEqualTo(AlarmStatus.ACKNOWLEDGED)
    }

    @Test
    fun `accept surfaces a 409 conflict (already resolved by someone else) as Error`() = runTest {
        coEvery { api.acceptAlarm("alarm-1") } returns Response.error(
            409,
            "{\"detail\":\"This assignment was already resolved by someone else\"}"
                .toResponseBody("application/json".toMediaType()),
        )

        val result = repository.acceptAlarm("alarm-1")

        assertThat(result).isInstanceOf(ApiResult.Error::class.java)
        assertThat((result as ApiResult.Error).httpCode).isEqualTo(409)
        assertThat(result.message).contains("already resolved")
    }

    @Test
    fun `decline returns the alarm still TRIGGERED (escalation continues)`() = runTest {
        coEvery { api.declineAlarm("alarm-1") } returns Response.success(alarm(AlarmStatus.TRIGGERED))

        val result = repository.declineAlarm("alarm-1")

        assertThat(result).isInstanceOf(ApiResult.Success::class.java)
        assertThat((result as ApiResult.Success).data.status).isEqualTo(AlarmStatus.TRIGGERED)
    }

    @Test
    fun `en-route transition returns EN_ROUTE`() = runTest {
        coEvery { api.alarmEnRoute("alarm-1") } returns Response.success(alarm(AlarmStatus.EN_ROUTE))

        val result = repository.markEnRoute("alarm-1")

        assertThat(result).isInstanceOf(ApiResult.Success::class.java)
        assertThat((result as ApiResult.Success).data.status).isEqualTo(AlarmStatus.EN_ROUTE)
    }

    @Test
    fun `en-route forbidden for a technician who did not accept surfaces 403`() = runTest {
        coEvery { api.alarmEnRoute("alarm-1") } returns Response.error(
            403,
            "{\"detail\":\"Only the accepting technician can mark EN_ROUTE\"}"
                .toResponseBody("application/json".toMediaType()),
        )

        val result = repository.markEnRoute("alarm-1")

        assertThat(result).isInstanceOf(ApiResult.Error::class.java)
        assertThat((result as ApiResult.Error).httpCode).isEqualTo(403)
    }

    @Test
    fun `resolve returns RESOLVED`() = runTest {
        coEvery { api.resolveAlarm("alarm-1") } returns Response.success(alarm(AlarmStatus.RESOLVED))

        val result = repository.resolveAlarm("alarm-1")

        assertThat(result).isInstanceOf(ApiResult.Success::class.java)
        assertThat((result as ApiResult.Success).data.status).isEqualTo(AlarmStatus.RESOLVED)
    }

    @Test
    fun `a network failure during accept never reports Success`() = runTest {
        coEvery { api.acceptAlarm("alarm-1") } throws IOException("timeout")

        val result = repository.acceptAlarm("alarm-1")

        assertThat(result).isInstanceOf(ApiResult.Error::class.java)
    }
}
