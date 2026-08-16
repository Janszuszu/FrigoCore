package pl.frigocore.service.data.model

import kotlinx.serialization.Serializable

@Serializable
data class LoginRequest(
    val username: String,
    val password: String,
)

@Serializable
data class LoginResponse(
    val access_token: String,
    val token_type: String = "bearer",
    val user: UserResponse,
)

@Serializable
data class UserResponse(
    val id: String,
    val username: String,
    val email: String,
    val full_name: String,
    val role: String,
    val is_active: Boolean,
    val object_ids: List<String> = emptyList(),
)

object UserRole {
    const val ADMIN = "admin"
    const val SERWISANT = "serwisant"
    const val KIEROWNIK = "kierownik"
    const val USER = "user"
}
