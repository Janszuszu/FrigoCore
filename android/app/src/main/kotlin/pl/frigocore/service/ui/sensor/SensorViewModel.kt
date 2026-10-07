package pl.frigocore.service.ui.sensor

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.ObjectRepository
import pl.frigocore.service.ui.common.Formatters
import java.time.Instant
import javax.inject.Inject

enum class HistoryRange(val label: String, val hours: Long) {
    H6("6H", 6),
    H24("24H", 24),
    D7("7D", 168),
}

data class ChartPoint(val time: Instant, val value: Double)

data class SensorUiState(
    val sensor: SensorResponse? = null,
    val range: HistoryRange = HistoryRange.H24,
    val points: List<ChartPoint> = emptyList(),
    val isLoadingHistory: Boolean = true,
    val error: String? = null,
) {
    val min: Double? get() = points.minOfOrNull { it.value }
    val max: Double? get() = points.maxOfOrNull { it.value }
    val avg: Double? get() = points.takeIf { it.isNotEmpty() }?.map { it.value }?.average()
}

@HiltViewModel
class SensorViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val objectRepository: ObjectRepository,
) : ViewModel() {

    private val objectId: String = checkNotNull(savedStateHandle["objectId"])
    private val sensorId: String = checkNotNull(savedStateHandle["sensorId"])

    private val _uiState = MutableStateFlow(SensorUiState())
    val uiState: StateFlow<SensorUiState> = _uiState.asStateFlow()

    fun selectRange(range: HistoryRange) {
        if (range == _uiState.value.range) return
        _uiState.value = _uiState.value.copy(range = range, isLoadingHistory = true, points = emptyList())
        refresh()
    }

    fun refresh() {
        val range = _uiState.value.range
        viewModelScope.launch {
            val sensor = async { objectRepository.getSensor(objectId, sensorId) }
            val history = async { objectRepository.history(sensorId, range.hours) }
            val sensorResult = sensor.await()
            val historyResult = history.await()
            // A range switch while this request was in flight makes it stale.
            if (_uiState.value.range != range) return@launch
            _uiState.value = _uiState.value.copy(
                sensor = (sensorResult as? ApiResult.Success)?.data ?: _uiState.value.sensor,
                points = (historyResult as? ApiResult.Success)?.data
                    ?.mapNotNull { m -> Formatters.parseInstant(m.received_at)?.let { ChartPoint(it, m.temperature) } }
                    ?: _uiState.value.points,
                isLoadingHistory = false,
                error = (historyResult as? ApiResult.Error)?.message ?: (sensorResult as? ApiResult.Error)?.message,
            )
        }
    }
}
