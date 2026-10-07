package pl.frigocore.service.ui.dashboard

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.AlarmStatus
import pl.frigocore.service.data.repository.AlarmRepository
import pl.frigocore.service.data.repository.ApiResult
import javax.inject.Inject

data class DashboardUiState(
    val isLoading: Boolean = false,
    val alarms: List<AlarmResponse> = emptyList(),
    val error: String? = null,
    val isClearingHistory: Boolean = false,
    /** One-shot result of "clear history", shown once and then consumed. */
    val clearHistoryResult: ApiResult<Int>? = null,
) {
    // Archived alarms are the ones cleared from history — they stay in the
    // backend for charts but are no longer listed here.
    private val visible: List<AlarmResponse> get() = alarms.filter { it.status != AlarmStatus.ARCHIVED }
    val active: List<AlarmResponse> get() = visible.filter { it.status == AlarmStatus.TRIGGERED }
    val acknowledged: List<AlarmResponse> get() = visible.filter { it.status == AlarmStatus.ACKNOWLEDGED }
    val enRoute: List<AlarmResponse> get() = visible.filter { it.status == AlarmStatus.EN_ROUTE }
    val recent: List<AlarmResponse> get() = visible.filter { it.status == AlarmStatus.RESOLVED }
    val isEmpty: Boolean get() = visible.isEmpty()
}

@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val alarmRepository: AlarmRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(DashboardUiState())
    val uiState: StateFlow<DashboardUiState> = _uiState.asStateFlow()

    fun refresh() {
        _uiState.value = _uiState.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            when (val result = alarmRepository.listAlarms()) {
                is ApiResult.Success -> _uiState.value = _uiState.value.copy(isLoading = false, alarms = result.data)
                is ApiResult.Error -> _uiState.value = _uiState.value.copy(isLoading = false, error = result.message)
            }
        }
    }

    fun clearHistory() {
        if (_uiState.value.isClearingHistory) return
        _uiState.value = _uiState.value.copy(isClearingHistory = true)
        viewModelScope.launch {
            val result = alarmRepository.archiveResolvedAlarms()
            _uiState.value = _uiState.value.copy(isClearingHistory = false, clearHistoryResult = result)
            refresh()
        }
    }

    fun clearHistoryResultShown() {
        _uiState.value = _uiState.value.copy(clearHistoryResult = null)
    }
}
