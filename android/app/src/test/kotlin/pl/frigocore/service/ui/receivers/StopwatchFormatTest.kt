package pl.frigocore.service.ui.receivers

import org.junit.Assert.assertEquals
import org.junit.Test

class StopwatchFormatTest {

    @Test
    fun `minutes and seconds under an hour`() {
        assertEquals("0:05", stopwatch(5))
        assertEquals("12:34", stopwatch(12 * 60 + 34))
    }

    @Test
    fun `hours once past sixty minutes`() {
        assertEquals("1:07:40", stopwatch(3600 + 7 * 60 + 40))
    }

    @Test
    fun `unknown duration`() {
        assertEquals("--:--", stopwatch(null))
    }
}
