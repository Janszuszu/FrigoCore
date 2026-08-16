package pl.frigocore.service.data.repository

/**
 * Outcome of a backend call. Deliberately has no "optimistic success" case —
 * a critical action (accept/decline/en-route/resolve) is only ever Success
 * once the backend has actually confirmed the state transition; a network
 * failure or a rejected precondition (409/403/400) must surface as Error so
 * the UI never claims an action succeeded that the server never applied.
 */
sealed class ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>()
    data class Error(val message: String, val httpCode: Int? = null) : ApiResult<Nothing>()
}

inline fun <T> ApiResult<T>.onSuccess(action: (T) -> Unit): ApiResult<T> {
    if (this is ApiResult.Success) action(data)
    return this
}
