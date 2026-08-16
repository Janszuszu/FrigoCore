package pl.frigocore.service.ui.alarm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.AlarmStatus
import pl.frigocore.service.data.model.ServiceAlarmPayload
import pl.frigocore.service.data.repository.AlarmRepository
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.fcm.AlarmNotificationHelper
import javax.inject.Inject

enum class AlarmActionInFlight { NONE, ACCEPT, DECLINE, EN_ROUTE, RESOLVE }

data class AlarmUiState(
    val alarmId: String = "",
    val siteName: String = "",
    val payloadAlarmType: String = "",
    val payloadSensorName: String = "",
    val payloadCreatedAt: String = "",
    val payloadDispatchedAt: String = "",
    val alarm: AlarmResponse? = null,
    val isLoadingDetail: Boolean = false,
    val actionInFlight: AlarmActionInFlight = AlarmActionInFlight.NONE,
    val actionError: String? = null,
    /** True once /events has been fetched at least once — drives the
     * event-history section rather than showing a permanent spinner. */
    val eventsLoaded: Boolean = false,
) {
    /** Effective status: the freshly-fetched alarm if we have it, otherwise
     * fall back to the FCM payload's implicit TRIGGERED state so the screen
     * never shows blank while the network round-trip is in flight. */
    val effectiveStatus: String get() = alarm?.status ?: AlarmStatus.TRIGGERED
}

@HiltViewModel
class AlarmViewModel @Inject constructor(
    private val alarmRepository: AlarmRepository,
    private val alarmNotificationHelper: AlarmNotificationHelper,
) : ViewModel() {

    private val _uiState = MutableStateFlow(AlarmUiState())
    val uiState: StateFlow<AlarmUiState> = _uiState.asStateFlow()

    fun initialize(payload: ServiceAlarmPayload, pendingAction: PendingAction?) {
        // Idempotent per alarm — a re-delivery of the same push (process
        // restart, duplicate FCM delivery) must not reset in-flight state,
        // but a genuinely new alarm (singleInstance AlarmActivity reusing
        // this ViewModel via onNewIntent) must always be picked up.
        if (_uiState.value.alarmId == payload.alarmId) return
        _uiState.value = AlarmUiState(
            alarmId = payload.alarmId,
            siteName = payload.siteName,
            payloadAlarmType = payload.alarmType,
            payloadSensorName = payload.sensorName,
            payloadCreatedAt = payload.createdAt,
            payloadDispatchedAt = payload.dispatchedAt,
        )
        loadDetail()
        when (pendingAction) {
            PendingAction.ACCEPT -> accept()
            PendingAction.DECLINE -> decline()
            null -> Unit
        }
    }

    fun loadDetail() {
        val alarmId = _uiState.value.alarmId
        if (alarmId.isBlank()) return
        _uiState.value = _uiState.value.copy(isLoadingDetail = true)
        viewModelScope.launch {
            when (val result = alarmRepository.getAlarm(alarmId)) {
                is ApiResult.Success -> _uiState.value = _uiState.value.copy(isLoadingDetail = false, alarm = result.data)
                is ApiResult.Error -> _uiState.value = _uiState.value.copy(isLoadingDetail = false)
            }
        }
    }

    fun accept() = runAction(AlarmActionInFlight.ACCEPT) { alarmRepository.acceptAlarm(it) }

    fun decline() = runAction(AlarmActionInFlight.DECLINE) { alarmRepository.declineAlarm(it) }

    fun markEnRoute() = runAction(AlarmActionInFlight.EN_ROUTE) { alarmRepository.markEnRoute(it) }

    fun resolve() = runAction(AlarmActionInFlight.RESOLVE) { alarmRepository.resolveAlarm(it) }

    fun dismissError() {
        _uiState.value = _uiState.value.copy(actionError = null)
    }

    /**
     * Fires a confirmed state-transition call. The UI never shows the new
     * status until the backend response lands — [AlarmActionInFlight] is the
     * only optimistic thing shown, and it always resolves to either the
     * confirmed [AlarmResponse] or a visible [AlarmUiState.actionError].
     */
    private fun runAction(action: AlarmActionInFlight, call: suspend (String) -> ApiResult<AlarmResponse>) {
        val alarmId = _uiState.value.alarmId
        if (alarmId.isBlank() || _uiState.value.actionInFlight != AlarmActionInFlight.NONE) return
        _uiState.value = _uiState.value.copy(actionInFlight = action, actionError = null)
        viewModelScope.launch {
            when (val result = call(alarmId)) {
                is ApiResult.Success -> {
                    _uiState.value = _uiState.value.copy(actionInFlight = AlarmActionInFlight.NONE, alarm = result.data)
                    // The insistent alarm sound/vibration is tied to the tray
                    // notification (FLAG_INSISTENT) — it must stop the moment
                    // the technician takes ANY confirmed action, not just on
                    // decline or final resolve, or PRZYJMUJĘ would leave it
                    // looping for the rest of the job.
                    if (action == AlarmActionInFlight.ACCEPT ||
                        action == AlarmActionInFlight.DECLINE ||
                        result.data.status == AlarmStatus.RESOLVED
                    ) {
                        alarmNotificationHelper.clearAlarm(alarmId)
                    }
                }
                is ApiResult.Error -> {
                    _uiState.value = _uiState.value.copy(
                        actionInFlight = AlarmActionInFlight.NONE,
                        actionError = result.message,
                    )
                }
            }
        }
    }
}

enum class PendingAction { ACCEPT, DECLINE }
