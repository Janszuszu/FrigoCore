package pl.frigocore.service.ui.meters

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch
import pl.frigocore.service.data.local.SelectedObjectStore
import pl.frigocore.service.data.model.Consumption
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.ObjectRepository
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.TemporalAdjusters
import java.util.Locale
import javax.inject.Inject

/** One card on the Liczniki screen: a meter, or all of them added up. */
data class MeterCard(
    val id: String,
    val name: String,
    /** The "all meters" group rather than one meter. */
    val isTotal: Boolean,
    /** Counter reading, or the counters added up. */
    val totalKwh: Double?,
    val powerW: Double?,
    val currentA: Double? = null,
    val voltageV: Double? = null,
    val consumption: Consumption,
)

data class MetersUiState(
    val isLoading: Boolean = true,
    val cards: List<MeterCard> = emptyList(),
    val error: String? = null,
)

/** One bar of the consumption chart; [kwh] is null for a day without data
 * or still to come. */
data class DayBar(val day: LocalDate, val kwh: Double?)

/** The backend cuts days at Polish midnight; the chart follows it. */
val MeterZone: ZoneId = ZoneId.of("Europe/Warsaw")

private fun Consumption.byDay(): Map<LocalDate, Double> =
    days.mapNotNull { d -> runCatching { LocalDate.parse(d.day) }.getOrNull()?.let { it to d.kwh } }.toMap()

/** "4,2 kWh"; one decimal is plenty for consumption. */
internal fun kwh(value: Double?): String =
    if (value == null) "—" else String.format(Locale.forLanguageTag("pl"), "%.1f kWh", value)

private val weekdays = listOf("Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd")

/** "Pn" … "Nd" under the week's bars. */
internal fun weekdayLabel(day: LocalDate): String = weekdays[day.dayOfWeek.value - 1]

private val dayTitleFormat = DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.forLanguageTag("pl"))

/** "środa 1 października" above the chart for a tapped bar. */
internal fun dayTitle(day: LocalDate): String = day.format(dayTitleFormat)

/** Monday to Sunday of [today]'s week. */
internal fun weekBars(consumption: Consumption, today: LocalDate): List<DayBar> {
    val used = consumption.byDay()
    val monday = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
    return (0L..6L).map { monday.plusDays(it) }.map { DayBar(it, used[it]) }
}

/** Every day of [today]'s month, 1st to the last. */
internal fun monthBars(consumption: Consumption, today: LocalDate): List<DayBar> {
    val used = consumption.byDay()
    return (1..today.lengthOfMonth()).map { today.withDayOfMonth(it) }.map { DayBar(it, used[it]) }
}

/** Meters of the object picked on the Objects screen; with two or more, an
 * "all meters" card goes first. */
@HiltViewModel
class MetersViewModel @Inject constructor(
    private val objectRepository: ObjectRepository,
    private val selectedObjectStore: SelectedObjectStore,
) : ViewModel() {

    private val _uiState = MutableStateFlow(MetersUiState())
    val uiState: StateFlow<MetersUiState> = _uiState.asStateFlow()

    init {
        // Another object picked: drop this one's meters at once instead of
        // showing them until the new object's data arrives.
        viewModelScope.launch {
            selectedObjectStore.selectedId.drop(1).collect { _uiState.value = MetersUiState() }
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
                _uiState.value = MetersUiState(isLoading = false)
                return@launch
            }
            val totalJob = async { objectRepository.metersTotal(objectId) }
            val metersResult = objectRepository.listMeters(objectId)
            if (metersResult is ApiResult.Error) {
                _uiState.value = _uiState.value.copy(isLoading = false, error = metersResult.message)
                return@launch
            }
            val meters = (metersResult as ApiResult.Success).data
                .filter { it.is_active }
                .sortedWith(compareBy({ it.display_order }, { it.name }))
            val total = (totalJob.await() as? ApiResult.Success)?.data

            // A different object picked while this poll was in flight makes it stale.
            if (selectedObjectStore.selectedId.value != stored) return@launch

            val cards = meters.map {
                MeterCard(it.id, it.name, false, it.total_kwh, it.power_w, it.current_a, it.voltage_v, it.consumption)
            }
            val sum = total?.takeIf { meters.size >= 2 }?.let {
                MeterCard("total", "Wszystkie liczniki", true, it.total_kwh, it.power_w, consumption = it.consumption)
            }
            _uiState.value = MetersUiState(isLoading = false, cards = listOfNotNull(sum) + cards)
        }
    }
}
