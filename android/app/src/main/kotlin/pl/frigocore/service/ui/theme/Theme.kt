package pl.frigocore.service.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val FrigoPrimary = Color(0xFF0B5FA5)
val FrigoPrimaryDark = Color(0xFF08406F)
val FrigoCritical = Color(0xFFD32F2F)
val FrigoCriticalDark = Color(0xFFB71C1C)
val FrigoWarning = Color(0xFFF57C00)
val FrigoOk = Color(0xFF2E7D32)
val FrigoBackground = Color(0xFFF4F6F8)
val FrigoSurface = Color(0xFFFFFFFF)

private val LightColors = lightColorScheme(
    primary = FrigoPrimary,
    onPrimary = Color.White,
    secondary = FrigoWarning,
    background = FrigoBackground,
    surface = FrigoSurface,
    error = FrigoCritical,
)

private val DarkColors = darkColorScheme(
    primary = FrigoPrimary,
    onPrimary = Color.White,
    secondary = FrigoWarning,
    error = FrigoCritical,
)

@Composable
fun FrigoCoreTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (darkTheme) DarkColors else LightColors
    MaterialTheme(colorScheme = colors, content = content)
}
