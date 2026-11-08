package app.noodle

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

val json = Json { ignoreUnknownKeys = true }

class ApiException(message: String, val code: Int = 0) : Exception(message)

data class PhoneReport(
    val id: String, val name: String, val battery: Int?, val charging: Boolean?,
    val latitude: Double?, val longitude: Double?, val accuracy: Float?,
)

class Api(private val prefs: Prefs) {
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .pingInterval(25, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val token = prefs.token
            val req = if (token.isNotEmpty()) chain.request().newBuilder().header("Authorization", "Bearer $token").build()
            else chain.request()
            chain.proceed(req)
        }
        .build()

    fun url(vararg segments: String): HttpUrl =
        prefs.baseUrl.toHttpUrl().newBuilder().apply { segments.forEach { addPathSegment(it) } }.build()

    private suspend fun post(url: HttpUrl, body: JsonObject): String = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url).post(body.toString().toRequestBody("application/json".toMediaType())).build()
        client.newCall(req).execute().use { r ->
            val text = r.body?.string().orEmpty()
            if (!r.isSuccessful) {
                val detail = runCatching { json.parseToJsonElement(text).jsonObject["detail"]?.jsonPrimitive?.content }.getOrNull()
                throw ApiException(detail ?: "HTTP ${r.code}", r.code)
            }
            text
        }
    }

    /** Trades the password for a token (the password itself is never kept). */
    suspend fun login(baseUrl: String, password: String, name: String): String {
        prefs.baseUrl = baseUrl
        val body = buildJsonObject { put("password", JsonPrimitive(password)); put("name", JsonPrimitive(name)) }
        val text = try {
            post(url("api", "auth", "app"), body)
        } catch (e: ApiException) {
            throw e
        } catch (e: Exception) {
            throw ApiException("Cannot reach ${prefs.baseUrl}: ${e.message}")
        }
        return json.parseToJsonElement(text).jsonObject["token"]!!.jsonPrimitive.content
    }

    suspend fun command(
        deviceId: String, key: String, on: Boolean? = null, brightness: Int? = null,
        toggle: Boolean = false, value: Double? = null, mode: String? = null,
    ) {
        val body = buildJsonObject {
            mode?.let { put("mode", JsonPrimitive(it)) }
            on?.let { put("on", JsonPrimitive(it)) }
            brightness?.let { put("brightness", JsonPrimitive(it)) }
            if (toggle) put("toggle", JsonPrimitive(true))
            value?.let { put("value", JsonPrimitive(it)) }
        }
        post(url("api", "devices", deviceId, "entities", key), body)
    }

    suspend fun devices(): List<Device> = withContext(Dispatchers.IO) {
        client.newCall(Request.Builder().url(url("api", "devices")).build()).execute().use { r ->
            if (!r.isSuccessful) throw ApiException("HTTP ${r.code}", r.code)
            json.decodeFromString(kotlinx.serialization.builtins.ListSerializer(Device.serializer()), r.body!!.string())
        }
    }

    suspend fun reportPhone(report: PhoneReport) {
        val body = buildJsonObject {
            put("name", JsonPrimitive(report.name))
            report.battery?.let { put("battery", JsonPrimitive(it)) }
            report.charging?.let { put("charging", JsonPrimitive(it)) }
            report.latitude?.let { put("latitude", JsonPrimitive(it)) }
            report.longitude?.let { put("longitude", JsonPrimitive(it)) }
            report.accuracy?.let { put("accuracy", JsonPrimitive(it.toDouble())) }
        }
        post(url("api", "phone", report.id), body)
    }
}
