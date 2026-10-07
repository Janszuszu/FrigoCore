package pl.frigocore.service.ui.overview

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import pl.frigocore.service.data.local.SelectedObjectStore
import pl.frigocore.service.data.model.AlarmResponse
import pl.frigocore.service.data.model.AlarmStatus
import pl.frigocore.service.data.model.MeasurementResponse
import pl.frigocore.service.data.model.ObjectResponse
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.data.repository.AlarmRepository
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.ObjectRepository
import pl.frigocore.service.ui.common.Formatters
import java.time.Duration
import java.time.Instant
import javax.inject.Inject

enum class SensorStatus { OK, ALARM, OFFLINE }

data class TempStats(val min: Double, val avg: Double, val max: Double)

data class SensorCard(
    val sensor: SensorResponse,
    val status: SensorStatus,
    val stats: TempStats? = null,
    /** Oldest-first 24 h values for the sparkline. */
    val spark: List<Double> = emptyList(),
)

data class OverviewUiState(
    val isLoading: Boolean = true,
    val objects: List<ObjectResponse> = emptyList(),
    val selectedObjectId: String? = null,
    val cards: List<SensorCard> = emptyList(),
    val openAlarms: List<AlarmResponse> = emptyList(),
    val error: String? = null,
) {
    val selectedObject: ObjectResponse? get() = objects.firstOrNull { it.id == selectedObjectId }
}

internal fun isOpen(alarm: AlarmResponse): Boolean =
    alarm.status == AlarmStatus.TRIGGERED || alarm.status == AlarmStatus.ACKNOWLEDGED || alarm.status == AlarmStatus.EN_ROUTE

internal fun tempStats(values: List<Double>): TempStats? =
    if (values.isEmpty()) null else TempStats(values.min(), values.average(), values.max())

internal fun sensorStatus(sensor: SensorResponse, openAlarms: List<AlarmResponse>, now: Instant = Instant.now()): SensorStatus =
    when {
        openAlarms.any { it.sensor_id == sensor.id && it.alarm_type != "offline" } -> SensorStatus.ALARM
        !Formatters.isOnline(sensor, now) -> SensorStatus.OFFLINE
        else -> SensorStatus.OK
    }

@HiltViewModel
class OverviewViewModel @Inject constructor(
    private val objectRepository: ObjectRepository,
    private val alarmRepository: AlarmRepository,
    private val selectedObjectStore: SelectedObjectStore,
) : ViewModel() {

    private val _uiState = MutableStateFlow(OverviewUiState())
    val uiState: StateFlow<OverviewUiState> = _uiState.asStateFlow()

    // 24 h history barely changes between 30 s polls; refetch it every few minutes.
    private var history: Map<String, List<MeasurementResponse>> = emptyMap()
    private var historyObjectId: String? = null
    private var historyFetchedAt: Instant = Instant.EPOCH

    fun selectObject(objectId: String) {
        if (objectId == _uiState.value.selectedObjectId) return
        selectedObjectStore.select(objectId)
        _uiState.value = _uiState.value.copy(selectedObjectId = objectId, cards = emptyList(), isLoading = true, error = null)
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            val objectsJob = async { objectRepository.listObjects() }
            val alarmsJob = async { alarmRepository.listAlarms() }
            val objectsResult = objectsJob.await()
            if (objectsResult is ApiResult.Error) {
                _uiState.value = _uiState.value.copy(isLoading = false, error = objectsResult.message)
                return@launch
            }
            val objects = (objectsResult as ApiResult.Success).data
            val stored = selectedObjectStore.selectedId.value
            val selectedId = objects.firstOrNull { it.id == stored }?.id ?: objects.firstOrNull()?.id
            val openAlarms = (alarmsJob.await() as? ApiResult.Success)?.data?.filter(::isOpen)
                ?: _uiState.value.openAlarms

            if (selectedId == null) {
                _uiState.value = OverviewUiState(isLoading = false, objects = objects)
                return@launch
            }

            val sensorsResult = objectRepository.listSensors(selectedId)
            if (sensorsResult is ApiResult.Error) {
                _uiState.value = _uiState.value.copy(isLoading = false, objects = objects, error = sensorsResult.message)
                return@launch
            }
            val sensors = (sensorsResult as ApiResult.Success).data
                .filter { it.is_active }
                .sortedWith(compareBy({ it.display_order }, { it.name }))

            val now = Instant.now()
            if (historyObjectId != selectedId || Duration.between(historyFetchedAt, now).toMinutes() >= 5) {
                history = sensors.map { s ->
                    async { s.id to ((objectRepository.history(s.id, 24, targetPoints = 60) as? ApiResult.Success)?.data) }
                }.awaitAll().mapNotNull { (id, data) -> data?.let { id to it } }.toMap()
                historyObjectId = selectedId
                historyFetchedAt = now
            }

            // A different object picked while this poll was in flight makes it stale.
            if (selectedObjectStore.selectedId.value != stored) return@launch

            _uiState.value = OverviewUiState(
                isLoading = false,
                objects = objects,
                selectedObjectId = selectedId,
                openAlarms = openAlarms,
                cards = sensors.map { sensor ->
                    val values = history[sensor.id].orEmpty().map { it.temperature }
                    SensorCard(sensor, sensorStatus(sensor, openAlarms, now), tempStats(values), values)
                },
            )
        }
    }
}
