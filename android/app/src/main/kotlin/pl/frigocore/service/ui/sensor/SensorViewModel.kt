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
import pl.frigocore.service.data.model.AlarmLimitsResponse
import pl.frigocore.service.data.model.SensorResponse
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.ObjectRepository
import pl.frigocore.service.ui.common.Formatters
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import javax.inject.Inject

enum class HistoryRange(val label: String, val hours: Long) {
    H1("1H", 1),
    H6("6H", 6),
    H24("24H", 24),
    D7("7D", 168),
}

data class ChartPoint(val time: Instant, val value: Double)

/** The page of a paged range [offset] pages from the current one (0 = the
 * page holding [now], -1 = the one before): a whole clock hour for 1H, a
 * 00-06 / 06-12 / 12-18 / 18-24 block for 6H, a calendar day for 24H.
 * Null for ranges that are not paged (7D). */
internal fun pageWindow(range: HistoryRange, offset: Int, now: LocalDateTime, zone: ZoneId): Pair<Instant, Instant>? {
    val current = when (range) {
        HistoryRange.H1 -> now.truncatedTo(ChronoUnit.HOURS)
        HistoryRange.H6 -> now.toLocalDate().atTime(now.hour / 6 * 6, 0)
        HistoryRange.H24 -> now.toLocalDate().atStartOfDay()
        HistoryRange.D7 -> return null
    }
    val start = current.plusHours(range.hours * offset)
    return start.atZone(zone).toInstant() to start.plusHours(range.hours).atZone(zone).toInstant()
}

data class SensorUiState(
    val sensor: SensorResponse? = null,
    val range: HistoryRange = HistoryRange.H24,
    /** Page shown in the 1H / 6H / 24H view: 0 = the current one, -1 = the one before, ... */
    val pageOffset: Int = 0,
    val limits: AlarmLimitsResponse? = null,
    val points: List<ChartPoint> = emptyList(),
    val isLoadingHistory: Boolean = true,
    val error: String? = null,
) {
    val minPoint: ChartPoint? get() = points.minByOrNull { it.value }
    val maxPoint: ChartPoint? get() = points.maxByOrNull { it.value }
    val min: Double? get() = minPoint?.value
    val max: Double? get() = maxPoint?.value
    val avg: Double? get() = points.takeIf { it.isNotEmpty() }?.map { it.value }?.average()

    /** Time axis span: the shown page of a paged range, null (= the data itself) for 7D. */
    val window: Pair<Instant, Instant>?
        get() = pageWindow(range, pageOffset, LocalDateTime.now(), ZoneId.systemDefault())
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
        _uiState.value = _uiState.value.copy(range = range, pageOffset = 0, isLoadingHistory = true, points = emptyList())
        refresh()
    }

    /** Pages a paged range by its own length; the future (offset > 0) is out of reach. */
    fun shiftPage(by: Int) {
        val state = _uiState.value
        val offset = (state.pageOffset + by).coerceAtMost(0)
        if (state.window == null || offset == state.pageOffset) return
        _uiState.value = state.copy(pageOffset = offset, isLoadingHistory = true, points = emptyList())
        refresh()
    }

    fun refresh() {
        val range = _uiState.value.range
        val pageOffset = _uiState.value.pageOffset
        val window = _uiState.value.window
        viewModelScope.launch {
            val sensor = async { objectRepository.getSensor(objectId, sensorId) }
            val limits = async { objectRepository.alarmLimits(sensorId) }
            val history = async {
                if (window == null) objectRepository.history(sensorId, range.hours)
                // The current page runs up to now; a past one is fetched whole.
                else objectRepository.history(sensorId, window.first, window.second.takeIf { pageOffset < 0 }, targetPoints = 144)
            }
            val sensorResult = sensor.await()
            val limitsResult = limits.await()
            val historyResult = history.await()
            // A range or page switch while this request was in flight makes it stale.
            if (_uiState.value.range != range || _uiState.value.pageOffset != pageOffset) return@launch
            _uiState.value = _uiState.value.copy(
                sensor = (sensorResult as? ApiResult.Success)?.data ?: _uiState.value.sensor,
                limits = (limitsResult as? ApiResult.Success)?.data ?: _uiState.value.limits,
                points = (historyResult as? ApiResult.Success)?.data
                    ?.mapNotNull { m -> Formatters.parseInstant(m.received_at)?.let { ChartPoint(it, m.temperature) } }
                    ?: _uiState.value.points,
                isLoadingHistory = false,
                error = (historyResult as? ApiResult.Error)?.message ?: (sensorResult as? ApiResult.Error)?.message,
            )
        }
    }
}
