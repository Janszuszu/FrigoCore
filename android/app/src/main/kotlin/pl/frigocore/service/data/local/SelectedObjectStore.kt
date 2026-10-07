package pl.frigocore.service.data.local

import android.content.Context
import androidx.core.content.edit
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/** The object shown on the Dashboard tab. Shared with the Objects tab (tap
 * an object to open it there) and remembered across app launches. */
@Singleton
class SelectedObjectStore @Inject constructor(@ApplicationContext context: Context) {

    private val prefs = context.getSharedPreferences("frigocore_ui", Context.MODE_PRIVATE)

    private val _selectedId = MutableStateFlow(prefs.getString(KEY_OBJECT_ID, null))
    val selectedId: StateFlow<String?> = _selectedId.asStateFlow()

    fun select(objectId: String) {
        prefs.edit { putString(KEY_OBJECT_ID, objectId) }
        _selectedId.value = objectId
    }

    private companion object {
        const val KEY_OBJECT_ID = "selected_object_id"
    }
}
