package pl.frigocore.service.ui.objects

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.AlarmStatus
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.data.repository.AlarmRepository
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.ObjectRepository
import javax.inject.Inject

data class ObjectDetailUiState(
    val isLoading: Boolean = true,
    val sensors: List<SensorResponse> = emptyList(),
    val openAlarms: List<AlarmResponse> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class ObjectDetailViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val objectRepository: ObjectRepository,
    private val alarmRepository: AlarmRepository,
) : ViewModel() {

    val objectId: String = checkNotNull(savedStateHandle["objectId"])

    private val _uiState = MutableStateFlow(ObjectDetailUiState())
    val uiState: StateFlow<ObjectDetailUiState> = _uiState.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            val sensors = async { objectRepository.listSensors(objectId) }
            val alarms = async { alarmRepository.listAlarms(objectId = objectId, limit = 50) }
            val sensorsResult = sensors.await()
            val openAlarms = (alarms.await() as? ApiResult.Success)?.data?.filter {
                it.status == AlarmStatus.TRIGGERED || it.status == AlarmStatus.ACKNOWLEDGED || it.status == AlarmStatus.EN_ROUTE
            }
            _uiState.value = when (sensorsResult) {
                is ApiResult.Success -> ObjectDetailUiState(
                    isLoading = false,
                    sensors = sensorsResult.data.filter { it.is_active },
                    openAlarms = openAlarms ?: _uiState.value.openAlarms,
                )
                is ApiResult.Error -> _uiState.value.copy(isLoading = false, error = sensorsResult.message)
            }
        }
    }
}
