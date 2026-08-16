package pl.frigocore.service.fcm

import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import pl.frigocore.service.data.local.SessionStore
import pl.frigocore.service.data.model.ServiceAlarmPayload
import pl.frigocore.service.data.repository.ApiResult
import pl.frigocore.service.data.repository.DeviceRepository
import javax.inject.Inject

@AndroidEntryPoint
class FrigoFcmService : FirebaseMessagingService() {

    @Inject lateinit var deviceRepository: DeviceRepository
    @Inject lateinit var sessionStore: SessionStore
    @Inject lateinit var alarmNotificationHelper: AlarmNotificationHelper
    @Inject lateinit var alarmDedupStore: AlarmDedupStore

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    /**
     * A refreshed token is worthless to the backend until it replaces the
     * old one there — this fires on install, app data clear, and periodic
     * FCM-internal rotation, so it must always re-register, not just once
     * at login.
     */
    override fun onNewToken(token: String) {
        super.onNewToken(token)
        if (sessionStore.accessToken == null) {
            // Not logged in yet — LoginViewModel registers the current
            // token right after a successful login instead.
            return
        }
        serviceScope.launch {
            when (val result = deviceRepository.registerToken(token)) {
                is ApiResult.Success -> Log.i(TAG, "FCM token registered: ${result.data.id}")
                is ApiResult.Error -> Log.w(TAG, "FCM token registration failed: ${result.message}")
            }
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        val payload = ServiceAlarmPayload.fromDataMap(message.data) ?: run {
            Log.w(TAG, "Ignoring non-SERVICE_ALARM or malformed push: ${message.data}")
            return
        }
        if (!payload.requiresAction) {
            // Contract guarantees SERVICE_ALARM always carries
            // requires_action=true; a payload that doesn't must not be
            // escalated to the critical alarm UI.
            Log.w(TAG, "SERVICE_ALARM without requires_action — ignoring: ${payload.alarmId}")
            return
        }
        if (alarmDedupStore.isDuplicate(payload)) {
            Log.i(TAG, "Duplicate delivery of assignment ${payload.assignmentId} — skipping re-alert")
            return
        }
        alarmDedupStore.markShown(payload)
        alarmNotificationHelper.showCriticalAlarm(payload)
    }

    private companion object {
        const val TAG = "FrigoFcmService"
    }
}
