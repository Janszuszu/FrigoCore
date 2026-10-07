package pl.frigocore.service.ui.theme

import androidx.compose.ui.text.TextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Dark navy palette shared with the web dashboard (frigocore.pl). The app is
// always dark — it mirrors the control-room look rather than the system theme.
val FrigoBackground = Color(0xFF060A11)
val FrigoSurface = Color(0xFF0B1422)
val FrigoSurfaceHigh = Color(0xFF111D2F)
val FrigoOutline = Color(0xFF1C2E47)
val FrigoAccent = Color(0xFF1EB8F2)
val FrigoText = Color(0xFFE8EEF6)
val FrigoTextMuted = Color(0xFF8A9BB2)

/** Equal-width digits, so a ticking clock or a changing reading doesn't
 * make its neighbours shuffle left and right. */
val TabularNumbers = TextStyle(fontFeatureSettings = "tnum")

val FrigoCritical = Color(0xFFEF4444)
val FrigoWarning = Color(0xFFF59E0B)
val FrigoOk = Color(0xFF22C55E)
val FrigoMin = Color(0xFF29ABF5)
val FrigoMax = Color(0xFFFF8A1F)

private val Colors = darkColorScheme(
    primary = FrigoAccent,
    onPrimary = FrigoBackground,
    secondary = FrigoWarning,
    background = FrigoBackground,
    onBackground = FrigoText,
    surface = FrigoSurface,
    onSurface = FrigoText,
    surfaceVariant = FrigoSurfaceHigh,
    onSurfaceVariant = FrigoTextMuted,
    surfaceContainer = FrigoSurface,
    surfaceContainerLow = FrigoSurface,
    surfaceContainerHigh = FrigoSurfaceHigh,
    surfaceContainerHighest = FrigoSurfaceHigh,
    outline = FrigoOutline,
    outlineVariant = FrigoOutline,
    error = FrigoCritical,
)

@Composable
fun FrigoCoreTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Colors, content = content)
}
