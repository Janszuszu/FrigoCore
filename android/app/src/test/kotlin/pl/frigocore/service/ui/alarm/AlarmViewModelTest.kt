package pl.frigocore.service.ui.alarm

import com.google.common.truth.Truth.assertThat
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import pl.frigocore.service.MainDispatcherRule
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.AlarmStatus
import pl.frigocore.service.data.model.ServiceAlarmPayload
import pl.frigocore.service.data.repository.AlarmRepository
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.fcm.AlarmNotificationHelper

/** Critical alarm handling end to end: seeding from the FCM payload,
 * fetching the authoritative status, and only ever reflecting a confirmed
 * backend response for accept/decline/en-route (never an optimistic one). */
class AlarmViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private lateinit var alarmRepository: AlarmRepository
    private lateinit var notificationHelper: AlarmNotificationHelper
    private lateinit var viewModel: AlarmViewModel

    private val payload = ServiceAlarmPayload(
        type = ServiceAlarmPayload.TYPE_SERVICE_ALARM,
        version = 1,
        alarmId = "alarm-1",
        assignmentId = "assignment-1",
        tier = 1,
        siteId = "site-1",
        siteName = "Chłodnia A",
        alarmType = "HIGH_TEMPERATURE",
        severity = "CRITICAL",
        title = "ALARM KRYTYCZNY",
        message = "Temperatura przekroczona",
        requiresAction = true,
        createdAt = "2026-08-16T10:00:00Z",
    )

    private fun alarm(status: String) = AlarmResponse(
        id = "alarm-1",
        alarm_type = "high_temperature",
        status = status,
        trigger_value = 9.0,
        detected_at = "2026-08-16T10:00:00Z",
        description = "Temperatura przekroczona",
        object_id = "site-1",
        sensor_id = "sensor-1",
        created_at = "2026-08-16T10:00:00Z",
        updated_at = "2026-08-16T10:00:00Z",
    )

    @Before
    fun setUp() {
        alarmRepository = mockk()
        notificationHelper = mockk(relaxed = true)
        viewModel = AlarmViewModel(alarmRepository, notificationHelper)
    }

    @Test
    fun `initialize seeds state from the push payload before the network call resolves`() = runTest {
        coEvery { alarmRepository.getAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.TRIGGERED))

        viewModel.initialize(payload, pendingAction = null)

        assertThat(viewModel.uiState.value.alarmId).isEqualTo("alarm-1")
        assertThat(viewModel.uiState.value.siteName).isEqualTo("Chłodnia A")
        assertThat(viewModel.uiState.value.effectiveStatus).isEqualTo(AlarmStatus.TRIGGERED)
    }

    @Test
    fun `initialize is idempotent — a second call, such as a process-restart redelivery, does not reset state`() = runTest {
        coEvery { alarmRepository.getAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.ACKNOWLEDGED))
        viewModel.initialize(payload, pendingAction = null)
        advanceUntilIdle()

        viewModel.initialize(payload, pendingAction = null)

        assertThat(viewModel.uiState.value.effectiveStatus).isEqualTo(AlarmStatus.ACKNOWLEDGED)
    }

    @Test
    fun `accept only reflects ACKNOWLEDGED after the backend confirms it`() = runTest {
        coEvery { alarmRepository.getAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.TRIGGERED))
        coEvery { alarmRepository.acceptAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.ACKNOWLEDGED))
        viewModel.initialize(payload, pendingAction = null)
        advanceUntilIdle()

        viewModel.accept()
        advanceUntilIdle()

        assertThat(viewModel.uiState.value.effectiveStatus).isEqualTo(AlarmStatus.ACKNOWLEDGED)
        assertThat(viewModel.uiState.value.actionError).isNull()
        assertThat(viewModel.uiState.value.actionInFlight).isEqualTo(AlarmActionInFlight.NONE)
    }

    @Test
    fun `a failed accept surfaces an error and does not advance the status`() = runTest {
        coEvery { alarmRepository.getAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.TRIGGERED))
        coEvery { alarmRepository.acceptAlarm("alarm-1") } returns ApiResult.Error("Brak połączenia z serwerem")
        viewModel.initialize(payload, pendingAction = null)
        advanceUntilIdle()

        viewModel.accept()
        advanceUntilIdle()

        assertThat(viewModel.uiState.value.effectiveStatus).isEqualTo(AlarmStatus.TRIGGERED)
        assertThat(viewModel.uiState.value.actionError).isEqualTo("Brak połączenia z serwerem")
        assertThat(viewModel.uiState.value.actionInFlight).isEqualTo(AlarmActionInFlight.NONE)
    }

    @Test
    fun `pendingAction ACCEPT from a notification action button fires automatically on initialize`() = runTest {
        coEvery { alarmRepository.getAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.TRIGGERED))
        coEvery { alarmRepository.acceptAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.ACKNOWLEDGED))

        viewModel.initialize(payload, pendingAction = PendingAction.ACCEPT)
        advanceUntilIdle()

        assertThat(viewModel.uiState.value.effectiveStatus).isEqualTo(AlarmStatus.ACKNOWLEDGED)
    }

    @Test
    fun `en-route only fires after acceptance and reflects the confirmed status`() = runTest {
        coEvery { alarmRepository.getAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.ACKNOWLEDGED))
        coEvery { alarmRepository.markEnRoute("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.EN_ROUTE))
        viewModel.initialize(payload, pendingAction = null)
        advanceUntilIdle()

        viewModel.markEnRoute()
        advanceUntilIdle()

        assertThat(viewModel.uiState.value.effectiveStatus).isEqualTo(AlarmStatus.EN_ROUTE)
    }

    @Test
    fun `a second action while one is in flight is ignored`() = runTest {
        coEvery { alarmRepository.getAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.TRIGGERED))
        coEvery { alarmRepository.acceptAlarm("alarm-1") } returns ApiResult.Success(alarm(AlarmStatus.ACKNOWLEDGED))
        viewModel.initialize(payload, pendingAction = null)
        advanceUntilIdle()

        viewModel.accept()
        viewModel.decline() // should be a no-op — an action is already in flight

        advanceUntilIdle()
        assertThat(viewModel.uiState.value.effectiveStatus).isEqualTo(AlarmStatus.ACKNOWLEDGED)
    }
}
