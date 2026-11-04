package app.noodle

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

/** Devices as the server pushes them over /api/ws. Nothing is polled: a change on the Pi arrives as a message. */
class Live(
    private val api: Api,
    private val scope: CoroutineScope,
    private val maxPause: Long = 15_000L,
    private val onNotification: (JsonObject) -> Unit = {},
    private val onUnauthorized: () -> Unit,
) {
    private val _devices = MutableStateFlow<Map<String, Device>>(emptyMap())
    private val _areas = MutableStateFlow<List<String>>(emptyList())
    private val _connected = MutableStateFlow(false)
    val devices: StateFlow<Map<String, Device>> = _devices
    val areas: StateFlow<List<String>> = _areas
    val connected: StateFlow<Boolean> = _connected

    private var job: Job? = null

    /** Keeps the socket open (reconnecting with a growing pause) until stop(). */
    fun start() {
        if (job?.isActive == true) return
        job = scope.launch {
            var pause = 1000L
            while (isActive) {
                val closed = CompletableDeferred<Int>()
                val wsUrl = api.url("api", "ws").toString().replaceFirst("http", "ws")
                val ws = api.client.newWebSocket(Request.Builder().url(wsUrl).build(), object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) { _connected.value = true; pause = 1000L }
                    override fun onMessage(webSocket: WebSocket, text: String) = handle(text)
                    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(1000, null) }
                    override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { closed.complete(code) }
                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                        closed.complete(if (response?.code == 401) 4401 else -1)
                    }
                })
                val code = try { closed.await() } finally { ws.cancel(); _connected.value = false }
                if (code == 4401) { onUnauthorized(); return@launch }
                delay(pause)
                pause = (pause * 2).coerceAtMost(maxPause)
            }
        }
    }

    fun stop() { job?.cancel(); job = null; _connected.value = false }

    private fun handle(text: String) {
        val msg = runCatching { json.parseToJsonElement(text).jsonObject }.getOrNull() ?: return
        when (msg["type"]?.jsonPrimitive?.content) {
            "snapshot" -> {
                val list = msg["devices"]?.jsonArray ?: JsonArray(emptyList())
                _devices.value = list
                    .mapNotNull {
                        runCatching { json.decodeFromJsonElement(Device.serializer(), it) }
                            .onFailure { e -> android.util.Log.w("Noodle", "bad device: ${e.message}") }.getOrNull()
                    }
                    .associateBy { it.id }
                android.util.Log.i("Noodle", "snapshot: ${list.size} devices, ${_devices.value.size} decoded")
                _areas.value = msg["areas"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList()
            }
            "device" -> msg["device"]?.let { el ->
                runCatching { json.decodeFromJsonElement(Device.serializer(), el) }.getOrNull()?.let { d ->
                    _devices.value = _devices.value + (d.id to d)
                }
            }
            "notification" -> onNotification(msg)
            "removed" -> msg["id"]?.jsonPrimitive?.content?.let { _devices.value = _devices.value - it }
        }
    }
}
