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
import pl.frigocore.service.data.repository.AuthRepository
import javax.inject.Inject

data class DashboardUiState(
    val isLoading: Boolean = false,
    val alarms: List<AlarmResponse> = emptyList(),
    val error: String? = null,
) {
    val active: List<AlarmResponse> get() = alarms.filter { it.status == AlarmStatus.TRIGGERED }
    val acknowledged: List<AlarmResponse> get() = alarms.filter { it.status == AlarmStatus.ACKNOWLEDGED }
    val enRoute: List<AlarmResponse> get() = alarms.filter { it.status == AlarmStatus.EN_ROUTE }
    val recent: List<AlarmResponse> get() = alarms.filter {
        it.status == AlarmStatus.RESOLVED || it.status == AlarmStatus.ARCHIVED
    }
}

@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val alarmRepository: AlarmRepository,
    private val authRepository: AuthRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(DashboardUiState())
    val uiState: StateFlow<DashboardUiState> = _uiState.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _uiState.value = _uiState.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            when (val result = alarmRepository.listAlarms()) {
                is ApiResult.Success -> _uiState.value = _uiState.value.copy(isLoading = false, alarms = result.data)
                is ApiResult.Error -> _uiState.value = _uiState.value.copy(isLoading = false, error = result.message)
            }
        }
    }

    fun logout(onDone: () -> Unit) {
        viewModelScope.launch {
            authRepository.logout()
            onDone()
        }
    }
}
