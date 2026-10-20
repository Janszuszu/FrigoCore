package pl.frigocore.service.ui.reports

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate

class ReportFormatTest {

    @Test
    fun `durations read as hours and minutes`() {
        assertEquals("6 h 14 min", duration(6 * 3600 + 14 * 60L))
        assertEquals("38 min", duration(38 * 60L))
        assertEquals("—", duration(null))
    }

    @Test
    fun `average run length is a stopwatch`() {
        assertEquals("4:05", average(245L * 4, 4))
        assertEquals("1:02:10", average(3730L, 1))
        assertEquals("—", average(100L, 0))
    }

    @Test
    fun `cycle counts take the Polish plural`() {
        assertEquals("1 cykl", cycles(1))
        assertEquals("3 cykle", cycles(3))
        assertEquals("12 cykli", cycles(12))
        assertEquals("22 cykle", cycles(22))
        assertEquals("64 cykle", cycles(64))
        assertEquals("65 cykli", cycles(65))
    }

    @Test
    fun `day arrows step through the reported days`() {
        val days = listOf(LocalDate.of(2026, 10, 20), LocalDate.of(2026, 10, 19), LocalDate.of(2026, 10, 18))
        val newest = ReportsUiState(isLoading = false, day = days[0], days = days)
        assertEquals(days[1], newest.older)
        assertNull(newest.newer)
        val oldest = newest.copy(day = days[2])
        assertNull(oldest.older)
        assertEquals(days[1], oldest.newer)
    }
}
