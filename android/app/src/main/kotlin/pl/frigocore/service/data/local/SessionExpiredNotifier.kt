package pl.frigocore.service.data.local

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Fan-out signal for "the backend just told us our token is no longer
 * valid" (a 401 from any authenticated call). The network layer emits;
 * the UI layer observes and forces a logout + return to the login screen
 * instead of letting each screen discover the same 401 independently.
 */
@Singleton
class SessionExpiredNotifier @Inject constructor() {
    private val _events = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    val events: SharedFlow<Unit> = _events.asSharedFlow()

    fun notifyExpired() {
        _events.tryEmit(Unit)
    }
}
