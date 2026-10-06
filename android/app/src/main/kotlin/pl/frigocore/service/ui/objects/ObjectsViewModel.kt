package pl.frigocore.service.ui.objects

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
import pl.frigocore.service.data.model.ObjectResponse
import pl.frigocore.service.data.repository.AlarmRepository
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.ObjectRepository
import javax.inject.Inject

data class ObjectsUiState(
    val isLoading: Boolean = true,
    val objects: List<ObjectResponse> = emptyList(),
    val activeAlarmsByObject: Map<String, Int> = emptyMap(),
    val error: String? = null,
)

/** Alarms that still need attention — shown as a badge on their object. */
internal fun openAlarmCounts(alarms: List<AlarmResponse>): Map<String, Int> =
    alarms.filter {
        it.status == AlarmStatus.TRIGGERED || it.status == AlarmStatus.ACKNOWLEDGED || it.status == AlarmStatus.EN_ROUTE
    }.groupingBy { it.object_id }.eachCount()

@HiltViewModel
class ObjectsViewModel @Inject constructor(
    private val objectRepository: ObjectRepository,
    private val alarmRepository: AlarmRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ObjectsUiState())
    val uiState: StateFlow<ObjectsUiState> = _uiState.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            val objects = async { objectRepository.listObjects() }
            val alarms = async { alarmRepository.listAlarms() }
            val objectsResult = objects.await()
            val alarmCounts = (alarms.await() as? ApiResult.Success)?.data?.let(::openAlarmCounts)
            _uiState.value = when (objectsResult) {
                is ApiResult.Success -> ObjectsUiState(
                    isLoading = false,
                    objects = objectsResult.data,
                    activeAlarmsByObject = alarmCounts ?: _uiState.value.activeAlarmsByObject,
                )
                // Keep the last good list on a transient failure — a dropped
                // poll must not blank the screen the user is looking at.
                is ApiResult.Error -> _uiState.value.copy(isLoading = false, error = objectsResult.message)
            }
        }
    }
}
