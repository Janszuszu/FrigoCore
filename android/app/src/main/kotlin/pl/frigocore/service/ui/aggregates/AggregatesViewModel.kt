package pl.frigocore.service.ui.aggregates

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch
import pl.frigocore.service.data.local.SelectedObjectStore
import pl.frigocore.service.data.model.AggregateResponse
import pl.frigocore.service.data.model.MeasurementResponse
import pl.frigocore.service.data.repository.AlarmRepository
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.ObjectRepository
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.overview.SensorCard
import pl.frigocore.service.ui.overview.SensorStatus
import pl.frigocore.service.ui.overview.isOpen
import pl.frigocore.service.ui.overview.sensorStatus
import pl.frigocore.service.ui.overview.tempStats
import pl.frigocore.service.ui.sensor.ChartPoint
import java.time.Duration
import java.time.Instant
import javax.inject.Inject

data class AggregateCard(
    val aggregate: AggregateResponse,
    /** The aggregate's sensors in the technician's order. */
    val sensors: List<SensorCard> = emptyList(),
) {
    val alarm: Boolean get() = sensors.any { it.status == SensorStatus.ALARM }
}

data class AggregatesUiState(
    val isLoading: Boolean = true,
    val aggregates: List<AggregateCard> = emptyList(),
    val objectId: String? = null,
    val error: String? = null,
)

/** Aggregates (agregaty) of the object picked on the Objects screen, each
 * with its sensors' current readings and 24 h history. */
@HiltViewModel
class AggregatesViewModel @Inject constructor(
    private val objectRepository: ObjectRepository,
    private val alarmRepository: AlarmRepository,
    private val selectedObjectStore: SelectedObjectStore,
) : ViewModel() {

    private val _uiState = MutableStateFlow(AggregatesUiState())
    val uiState: StateFlow<AggregatesUiState> = _uiState.asStateFlow()

    // 24 h history barely changes between 30 s polls; refetch it every few minutes.
    private var history: Map<String, List<MeasurementResponse>> = emptyMap()
    private var historyObjectId: String? = null
    private var historyFetchedAt: Instant = Instant.EPOCH

    init {
        // Another object picked: drop this one's aggregates at once instead of
        // showing them until the new object's data arrives.
        viewModelScope.launch {
            selectedObjectStore.selectedId.drop(1).collect { _uiState.value = AggregatesUiState() }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            val objectsResult = objectRepository.listObjects()
            if (objectsResult is ApiResult.Error) {
                _uiState.value = _uiState.value.copy(isLoading = false, error = objectsResult.message)
                return@launch
            }
            val objects = (objectsResult as ApiResult.Success).data
            val stored = selectedObjectStore.selectedId.value
            val objectId = objects.firstOrNull { it.id == stored }?.id ?: objects.firstOrNull()?.id
            if (objectId == null) {
                _uiState.value = AggregatesUiState(isLoading = false)
                return@launch
            }
            val alarmsJob = async { alarmRepository.listAlarms(objectId = objectId) }
            val sensorsJob = async { objectRepository.listSensors(objectId) }
            val aggregatesResult = objectRepository.listAggregates(objectId)
            if (aggregatesResult is ApiResult.Error) {
                _uiState.value = _uiState.value.copy(isLoading = false, error = aggregatesResult.message)
                return@launch
            }
            val aggregates = (aggregatesResult as ApiResult.Success).data
                .filter { it.is_active }
                .sortedWith(compareBy({ it.display_order }, { it.name }))
            val sensors = (sensorsJob.await() as? ApiResult.Success)?.data.orEmpty()
                .filter { it.is_active }
                .associateBy { it.id }

            val openAlarms = (alarmsJob.await() as? ApiResult.Success)?.data.orEmpty().filter(::isOpen)

            // A different object picked while this poll was in flight makes it stale.
            if (selectedObjectStore.selectedId.value != stored) return@launch

            val now = Instant.now()
            fun publish() {
                _uiState.value = AggregatesUiState(
                    isLoading = false,
                    objectId = objectId,
                    aggregates = aggregates.map { aggregate ->
                        AggregateCard(
                            aggregate,
                            aggregate.sensor_ids.mapNotNull { sensors[it] }.map { sensor ->
                                val points = history[sensor.id].orEmpty().mapNotNull { m ->
                                    Formatters.parseInstant(m.received_at)?.let { ChartPoint(it, m.temperature) }
                                }
                                SensorCard(sensor, sensorStatus(sensor, openAlarms, now), tempStats(points.map { it.value }), points)
                            },
                        )
                    },
                )
            }

            val sensorIds = aggregates.flatMap { it.sensor_ids }.filter { it in sensors }.toSet()
            if (historyObjectId != objectId || !history.keys.containsAll(sensorIds) ||
                Duration.between(historyFetchedAt, now).toMinutes() >= 5
            ) {
                // Show the nameplate and current readings straight away; the charts follow.
                if (historyObjectId != objectId) history = emptyMap()
                publish()
                val fetched = sensorIds.map { id ->
                    async { id to ((objectRepository.history(id, 24, targetPoints = 144) as? ApiResult.Success)?.data) }
                }.awaitAll().mapNotNull { (id, data) -> data?.let { id to it } }.toMap()
                if (selectedObjectStore.selectedId.value != stored) return@launch
                history = fetched
                historyObjectId = objectId
                historyFetchedAt = now
            }
            publish()
        }
    }
}
