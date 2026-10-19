package pl.frigocore.service.ui.sensor

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId

class DayChartTest {

    private val warsaw = ZoneId.of("Europe/Warsaw")
    private val now = LocalDateTime.of(2026, 10, 19, 14, 37)

    @Test
    fun `24H page is the calendar day`() {
        val (start, end) = pageWindow(HistoryRange.H24, 0, now, warsaw)!!
        assertEquals(Instant.parse("2026-10-18T22:00:00Z"), start)
        assertEquals(Instant.parse("2026-10-19T22:00:00Z"), end)
    }

    @Test
    fun `24H negative offset steps back whole days, DST day is 25 hours`() {
        val (start, end) = pageWindow(HistoryRange.H24, -1, LocalDateTime.of(2026, 10, 26, 9, 0), warsaw)!!
        assertEquals(Instant.parse("2026-10-24T22:00:00Z"), start)
        assertEquals(Instant.parse("2026-10-25T23:00:00Z"), end)
    }

    @Test
    fun `1H page is the clock hour, paged by 60 minutes`() {
        assertEquals(
            Instant.parse("2026-10-19T12:00:00Z") to Instant.parse("2026-10-19T13:00:00Z"),
            pageWindow(HistoryRange.H1, 0, now, warsaw),
        )
        assertEquals(
            Instant.parse("2026-10-19T10:00:00Z") to Instant.parse("2026-10-19T11:00:00Z"),
            pageWindow(HistoryRange.H1, -2, now, warsaw),
        )
    }

    @Test
    fun `6H page is a quarter of the day, paged by 6 hours`() {
        // 14:37 local sits in the 12:00-18:00 block.
        assertEquals(
            Instant.parse("2026-10-19T10:00:00Z") to Instant.parse("2026-10-19T16:00:00Z"),
            pageWindow(HistoryRange.H6, 0, now, warsaw),
        )
        // Three back: the previous day's 18:00-24:00.
        assertEquals(
            Instant.parse("2026-10-18T16:00:00Z") to Instant.parse("2026-10-18T22:00:00Z"),
            pageWindow(HistoryRange.H6, -3, now, warsaw),
        )
    }

    @Test
    fun `7D is not paged`() {
        assertNull(pageWindow(HistoryRange.D7, 0, now, warsaw))
    }

    @Test
    fun `axis labels read minutes for 1H and close the day as 24 00`() {
        assertEquals(listOf("00", "30", "60"), pageAxisLabels(HistoryRange.H1, pageWindow(HistoryRange.H1, 0, now, warsaw)!!, warsaw))
        assertEquals(listOf("00:00", "12:00", "24:00"), pageAxisLabels(HistoryRange.H24, pageWindow(HistoryRange.H24, 0, now, warsaw)!!, warsaw))
        assertEquals(listOf("18:00", "21:00", "24:00"), pageAxisLabels(HistoryRange.H6, pageWindow(HistoryRange.H6, -3, now, warsaw)!!, warsaw))
    }

    @Test
    fun `normal band pads the thresholds to whole degrees`() {
        assertEquals(-5.0 to 11.0, normalBandBounds(-2.0, 8.0))
        // A narrow band still gets at least 2 degrees either side.
        assertEquals(-23.0 to -13.0, normalBandBounds(-21.0, -15.0))
    }

    @Test
    fun `incomplete band falls back to the data`() {
        assertNull(normalBandBounds(null, 8.0))
        assertNull(normalBandBounds(-2.0, null))
        assertNull(normalBandBounds(5.0, 5.0))
    }

    @Test
    fun `value axis snaps to round steps`() {
        // The data range of the 20.10 mockup: 0..20 every 5 degrees.
        assertEquals(Triple(0.0, 20.0, 5.0), niceAxis(0.0, 20.0))
        assertEquals(Triple(-5.0, 15.0, 5.0), niceAxis(-5.0, 11.0))
        assertEquals(Triple(-24.0, -12.0, 2.0), niceAxis(-23.0, -13.0))
        // Never finer than a whole unit, so labels stay integers.
        assertEquals(Triple(3.0, 5.0, 1.0), niceAxis(3.0, 5.0))
    }
}
