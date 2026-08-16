package pl.frigocore.service.data.model

import kotlinx.serialization.Serializable

@Serializable
data class DeviceTokenRegister(
    val fcm_token: String,
    val platform: String = "android",
)

@Serializable
data class DeviceTokenResponse(
    val id: String,
    val user_id: String,
    val platform: String,
    val is_active: Boolean,
    val last_seen_at: String? = null,
    val created_at: String,
    val updated_at: String,
)
