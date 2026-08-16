package pl.frigocore.service.data.repository

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import retrofit2.Response
import java.io.IOException

/**
 * Runs a Retrofit suspend call and converts it to an [ApiResult], collapsing
 * both transport failures (no connectivity, timeout) and rejected requests
 * (4xx/5xx) into an explicit Error rather than letting either escape as an
 * unhandled exception or a silently-null body.
 */
suspend fun <T> safeApiCall(block: suspend () -> Response<T>): ApiResult<T> {
    return try {
        val response = block()
        if (response.isSuccessful) {
            val body = response.body()
            if (body != null) {
                ApiResult.Success(body)
            } else {
                ApiResult.Error("Empty response from server", response.code())
            }
        } else {
            ApiResult.Error(extractErrorDetail(response), response.code())
        }
    } catch (io: IOException) {
        ApiResult.Error("Brak połączenia z serwerem")
    } catch (e: Exception) {
        ApiResult.Error(e.message ?: "Nieznany błąd")
    }
}

/** Retrofit endpoints that return no body (e.g. DELETE /devices/{id}) —
 * same success/failure collapsing as [safeApiCall] without a body payload. */
suspend fun safeApiCallUnit(block: suspend () -> Response<Unit>): ApiResult<Unit> {
    return try {
        val response = block()
        if (response.isSuccessful) {
            ApiResult.Success(Unit)
        } else {
            ApiResult.Error(extractErrorDetail(response), response.code())
        }
    } catch (io: IOException) {
        ApiResult.Error("Brak połączenia z serwerem")
    } catch (e: Exception) {
        ApiResult.Error(e.message ?: "Nieznany błąd")
    }
}

private fun extractErrorDetail(response: Response<*>): String {
    val raw = response.errorBody()?.string()
    if (raw.isNullOrBlank()) return "Błąd serwera (${response.code()})"
    return runCatching {
        val json = Json { ignoreUnknownKeys = true }
        val element = json.parseToJsonElement(raw)
        element.jsonObject["detail"]?.jsonPrimitive?.content
    }.getOrNull() ?: "Błąd serwera (${response.code()})"
}
