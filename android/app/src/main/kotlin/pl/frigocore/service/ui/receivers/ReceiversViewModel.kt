package pl.frigocore.service.ui.receivers

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
import pl.frigocore.service.data.model.MeasurementResponse
import pl.frigocore.service.data.model.ReceiverResponse
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.ObjectRepository
import pl.frigocore.service.ui.common.Formatters
import pl.frigocore.service.ui.overview.TempStats
import pl.frigocore.service.ui.overview.tempStats
import pl.frigocore.service.ui.sensor.ChartPoint
import java.time.Duration
import java.time.Instant
import javax.inject.Inject

data class ReceiverCard(
    val receiver: ReceiverResponse,
    /** Oldest-first 24 h chamber readings. */
    val chamber: List<ChartPoint> = emptyList(),
    val stats: TempStats? = null,
)

data class ReceiversUiState(
    val isLoading: Boolean = true,
    val cards: List<ReceiverCard> = emptyList(),
    val objectId: String? = null,
)

/** Receivers of the object picked on the Objects screen. An object with
 * none configured (or a backend that doesn't know receivers yet) yields an
 * empty list, and the screen falls back to the plain sensor dashboard. */
@HiltViewModel
class ReceiversViewModel @Inject constructor(
    private val objectRepository: ObjectRepository,
    private val selectedObjectStore: SelectedObjectStore,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ReceiversUiState())
    val uiState: StateFlow<ReceiversUiState> = _uiState.asStateFlow()

    // 24 h history barely changes between 30 s polls; refetch it every few minutes.
    private var history: Map<String, List<MeasurementResponse>> = emptyMap()
    private var historyObjectId: String? = null
    private var historyFetchedAt: Instant = Instant.EPOCH

    fun refresh() {
        viewModelScope.launch {
            val objects = (objectRepository.listObjects() as? ApiResult.Success)?.data.orEmpty()
            val stored = selectedObjectStore.selectedId.value
            val objectId = objects.firstOrNull { it.id == stored }?.id ?: objects.firstOrNull()?.id
            if (objectId == null) {
                _uiState.value = ReceiversUiState(isLoading = false)
                return@launch
            }
            val receivers = (objectRepository.listReceivers(objectId) as? ApiResult.Success)?.data.orEmpty()
                .filter { it.is_active }
                .sortedWith(compareBy({ it.display_order }, { it.name }))

            // Only the chamber is charted; the evaporator is shown as its current reading.
            val sensorIds = receivers.mapNotNull { it.chamber_sensor_id }.toSet()
            val now = Instant.now()
            if (historyObjectId != objectId || !history.keys.containsAll(sensorIds) ||
                Duration.between(historyFetchedAt, now).toMinutes() >= 5
            ) {
                history = sensorIds.map { id ->
                    async { id to ((objectRepository.history(id, 24, targetPoints = 144) as? ApiResult.Success)?.data) }
                }.awaitAll().mapNotNull { (id, data) -> data?.let { id to it } }.toMap()
                historyObjectId = objectId
                historyFetchedAt = now
            }

            // A different object picked while this poll was in flight makes it stale.
            if (selectedObjectStore.selectedId.value != stored) return@launch

            fun points(sensorId: String?) = history[sensorId].orEmpty().mapNotNull { m ->
                Formatters.parseInstant(m.received_at)?.let { ChartPoint(it, m.temperature) }
            }
            _uiState.value = ReceiversUiState(
                isLoading = false,
                objectId = objectId,
                cards = receivers.map { r ->
                    val chamber = points(r.chamber_sensor_id)
                    ReceiverCard(r, chamber, tempStats(chamber.map { it.value }))
                },
            )
        }
    }
}
