package pl.frigocore.service.ui.reports

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch
import pl.frigocore.service.data.local.SelectedObjectStore
import pl.frigocore.service.data.model.AggregateDayReportResponse
import pl.frigocore.service.data.model.ReceiverDayReportResponse
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.ObjectRepository
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import javax.inject.Inject

data class ReportsUiState(
    val isLoading: Boolean = true,
    /** The day shown; null before the first report exists. */
    val day: LocalDate? = null,
    /** Days with a report, newest first. */
    val days: List<LocalDate> = emptyList(),
    val receivers: List<ReceiverDayReportResponse> = emptyList(),
    val aggregates: List<AggregateDayReportResponse> = emptyList(),
    val error: String? = null,
) {
    private val index: Int get() = days.indexOf(day)
    /** The day before the shown one that has a report, if any. */
    val older: LocalDate? get() = days.getOrNull(index + 1).takeIf { index >= 0 }
    val newer: LocalDate? get() = if (index > 0) days[index - 1] else null
}

/** "6 h 14 min", "38 min", "0 min". */
internal fun duration(seconds: Long?): String {
    if (seconds == null) return "—"
    val minutes = (seconds + 30) / 60
    val h = minutes / 60
    val m = minutes % 60
    return if (h > 0) "$h h $m min" else "$m min"
}

/** A run's average length as a stopwatch: "4:05", "1:02:10". */
internal fun average(totalSeconds: Long, count: Int): String {
    if (count == 0) return "—"
    val s = totalSeconds / count
    val h = s / 3600
    return if (h > 0) "%d:%02d:%02d".format(h, s % 3600 / 60, s % 60) else "%d:%02d".format(s / 60, s % 60)
}

private val dayFormat = DateTimeFormatter.ofPattern("EEEE, dd.MM.yyyy", Locale.forLanguageTag("pl"))

/** "Poniedziałek, 19.10.2026". */
internal fun dayHeading(day: LocalDate): String = day.format(dayFormat).replaceFirstChar { it.uppercase() }

/** Raport: the receivers' analysed days of the object picked on the
 * Objects screen, one day at a time. */
@HiltViewModel
class ReportsViewModel @Inject constructor(
    private val objectRepository: ObjectRepository,
    private val selectedObjectStore: SelectedObjectStore,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ReportsUiState())
    val uiState: StateFlow<ReportsUiState> = _uiState.asStateFlow()

    init {
        // Another object: start again on its newest day.
        viewModelScope.launch {
            selectedObjectStore.selectedId.drop(1).collect {
                _uiState.value = ReportsUiState()
                load(null)
            }
        }
    }

    fun refresh() = load(_uiState.value.day)

    fun showDay(day: LocalDate) {
        _uiState.value = _uiState.value.copy(isLoading = true, day = day, receivers = emptyList(), aggregates = emptyList())
        load(day)
    }

    private fun load(day: LocalDate?) {
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
                _uiState.value = ReportsUiState(isLoading = false)
                return@launch
            }
            val result = objectRepository.receiverReports(objectId, day?.toString())
            // Another object or day picked while this was in flight.
            if (selectedObjectStore.selectedId.value != stored || (day != null && _uiState.value.day != day)) return@launch
            _uiState.value = when (result) {
                is ApiResult.Error -> _uiState.value.copy(isLoading = false, error = result.message)
                is ApiResult.Success -> ReportsUiState(
                    isLoading = false,
                    day = result.data.day?.let(LocalDate::parse),
                    days = result.data.days.mapNotNull { runCatching { LocalDate.parse(it) }.getOrNull() },
                    receivers = result.data.receivers,
                    aggregates = result.data.aggregates,
                )
            }
        }
    }
}
