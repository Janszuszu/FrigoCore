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
 * 00-06 / 06-12 / 12-18 / 18-24 block for 6H. 24H opens on the last 24 hours
 * up to the end of the current hour; one page back is yesterday 00-24, then
 * the calendar days before it. Null for ranges that are not paged (7D). */
internal fun pageWindow(range: HistoryRange, offset: Int, now: LocalDateTime, zone: ZoneId): Pair<Instant, Instant>? {
    if (range == HistoryRange.H24 && offset == 0) {
        val end = now.truncatedTo(ChronoUnit.HOURS).plusHours(1).atZone(zone).toInstant()
        return end.minusSeconds(24 * 3600) to end
    }
    val current = when (range) {
        HistoryRange.H1 -> now.truncatedTo(ChronoUnit.HOURS)
        HistoryRange.H6 -> now.toLocalDate().atTime(now.hour / 6 * 6, 0)
        HistoryRange.H24 -> now.toLocalDate().atStartOfDay()
        HistoryRange.D7 -> return null
    }
    val start = current.plusHours(range.hours * offset)
    return start.atZone(zone).toInstant() to start.plusHours(range.hours).atZone(zone).toInstant()
}

/** [window] slid by [millis] (negative = back in time), its end held at or
 * before [latestEnd] so the chart never runs into the future. */
internal fun slideWindow(window: Pair<Instant, Instant>, millis: Long, latestEnd: Instant): Pair<Instant, Instant> {
    val length = window.second.toEpochMilli() - window.first.toEpochMilli()
    val start = (window.first.toEpochMilli() + millis).coerceAtMost(latestEnd.toEpochMilli() - length)
    return Instant.ofEpochMilli(start) to Instant.ofEpochMilli(start + length)
}

data class SensorUiState(
    val sensor: SensorResponse? = null,
    val range: HistoryRange = HistoryRange.H24,
    /** Page shown in the 1H / 6H / 24H view: 0 = the current one, -1 = the one before, ... */
    val pageOffset: Int = 0,
    /** Start of a window slid off the page grid by dragging the chart; null = on [pageOffset]. */
    val customStart: Instant? = null,
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

    /** Time axis span: the shown page (or slid window) of a paged range, null (= the data itself) for 7D. */
    val window: Pair<Instant, Instant>?
        get() = customStart?.let { it to it.plusSeconds(range.hours * 3600) }
            ?: pageWindow(range, pageOffset, LocalDateTime.now(), ZoneId.systemDefault())

    /** End of the current page: no window may reach past it. */
    val latestEnd: Instant?
        get() = pageWindow(range, 0, LocalDateTime.now(), ZoneId.systemDefault())?.second
}

@HiltViewModel
class SensorViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val objectRepository: ObjectRepository,
) : ViewModel() {

    private var objectId: String = savedStateHandle["objectId"] ?: ""
    private var sensorId: String = savedStateHandle["sensorId"] ?: ""

    /** Points this chart at a sensor; the full-screen overlay has no nav arguments. */
    fun open(objectId: String, sensorId: String) {
        if (objectId == this.objectId && sensorId == this.sensorId) return
        this.objectId = objectId
        this.sensorId = sensorId
        _uiState.value = SensorUiState()
        refresh()
    }

    private val _uiState = MutableStateFlow(SensorUiState())
    val uiState: StateFlow<SensorUiState> = _uiState.asStateFlow()

    fun selectRange(range: HistoryRange) {
        if (range == _uiState.value.range) return
        _uiState.value = _uiState.value.copy(range = range, pageOffset = 0, customStart = null, isLoadingHistory = true, points = emptyList())
        refresh()
    }

    /** Pages a paged range by its own length; the future (offset > 0) is out of reach. */
    fun shiftPage(by: Int) {
        val state = _uiState.value
        val window = state.window ?: return
        if (state.customStart != null) {
            val length = window.second.toEpochMilli() - window.first.toEpochMilli()
            val slid = slideWindow(window, by * length, state.latestEnd ?: return)
            if (slid.first == window.first) return
            _uiState.value = state.copy(customStart = slid.first, isLoadingHistory = true, points = emptyList())
        } else {
            val offset = (state.pageOffset + by).coerceAtMost(0)
            if (offset == state.pageOffset) return
            _uiState.value = state.copy(pageOffset = offset, isLoadingHistory = true, points = emptyList())
        }
        refresh()
    }

    /** Slides the window by [millis] after the chart was dragged under its
     * crosshair. The old readings stay on screen until the new ones land. */
    fun panBy(millis: Long) {
        val state = _uiState.value
        val window = state.window ?: return
        val slid = slideWindow(window, millis, state.latestEnd ?: return)
        if (slid.first == window.first) return
        _uiState.value = state.copy(customStart = slid.first)
        refresh()
    }

    fun refresh() {
        if (sensorId.isEmpty()) return
        val objectId = objectId
        val sensorId = sensorId
        val range = _uiState.value.range
        val pageOffset = _uiState.value.pageOffset
        val customStart = _uiState.value.customStart
        val window = _uiState.value.window
        viewModelScope.launch {
            val sensor = async { objectRepository.getSensor(objectId, sensorId) }
            val limits = async { objectRepository.alarmLimits(sensorId) }
            val history = async {
                if (window == null) objectRepository.history(sensorId, range.hours)
                // A window reaching past now runs up to now; a past one is fetched whole.
                else objectRepository.history(sensorId, window.first, window.second.takeIf { it.isBefore(Instant.now()) }, targetPoints = 144)
            }
            val sensorResult = sensor.await()
            val limitsResult = limits.await()
            val historyResult = history.await()
            // A range, page or slide change while this request was in flight makes it stale.
            val now = _uiState.value
            if (sensorId != this@SensorViewModel.sensorId || now.range != range || now.pageOffset != pageOffset || now.customStart != customStart) return@launch
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
