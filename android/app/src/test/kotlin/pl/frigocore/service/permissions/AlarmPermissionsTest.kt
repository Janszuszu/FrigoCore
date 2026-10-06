package pl.frigocore.service.permissions

import android.provider.Settings
import androidx.test.core.app.ApplicationProvider
import com.google.common.truth.Truth.assertThat
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class AlarmPermissionsTest {

    private val context = ApplicationProvider.getApplicationContext<android.app.Application>()

    @Test
    fun `full-screen intent settings intent targets this app's package`() {
        val intent = AlarmPermissions.fullScreenIntentSettingsIntent(context)
        assertThat(intent.action).isEqualTo(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT)
        assertThat(intent.data?.schemeSpecificPart).isEqualTo(context.packageName)
    }

    @Test
    fun `app notification settings intent targets this app's package`() {
        val intent = AlarmPermissions.appNotificationSettingsIntent(context)
        assertThat(intent.action).isEqualTo(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
        assertThat(intent.getStringExtra(Settings.EXTRA_APP_PACKAGE)).isEqualTo(context.packageName)
    }
}
