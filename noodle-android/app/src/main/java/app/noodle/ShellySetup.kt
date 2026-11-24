package app.noodle

import android.annotation.SuppressLint
import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiInfo
import android.net.wifi.WifiManager
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.FormBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Putting a brand-new Shelly on the home Wi-Fi with this phone, the same way the hub does it (hotspot.py on the hub).
 *
 * A Shelly that was never set up (or was reset) opens its own open Wi-Fi network, named like `shelly1-A4CF12B3C4D5`
 * or `ShellyPlus1PM-...`, and answers at 192.168.33.1. The phone joins that network for a moment (Android asks the
 * user first), tells the Shelly the home network's name and password, lets go of it so the phone goes back home,
 * and then looks for the Shelly on the home network to add it to the hub.
 *
 * Nothing scans in the background: the networks are listed only while the setup screen is open. The Wi-Fi
 * password goes to the Shelly and is never stored or logged.
 */
object ShellySetup {
    const val SETUP_ADDRESS = "192.168.33.1" // where every Shelly answers on its own network
    const val REACH_SECONDS = 30 // how long the Shelly gets to answer once the phone is on its network
    const val JOIN_SECONDS = 120 // how long a newly set up Shelly gets to show up on the home network

    const val LOCKED = "This Shelly has a password set. Reset it (hold its button for about 10 seconds), then search again"
    const val OUT_OF_REACH = "Could not join the Shelly's Wi-Fi. Move it closer to this phone, then search again"

    private val AP = Regex("^shelly[a-z0-9]*(-[a-z0-9]+)*-[0-9a-f]{6,12}$", RegexOption.IGNORE_CASE)

    /** The network a Shelly opens while it is not set up yet: 'shelly1-A4CF12', 'shellyplug-s-7C87CE', ... */
    fun isShellyAp(ssid: String) = AP.matches(ssid)

    /** 'shellyplug-s-7C87CE' -> 'Shelly plug-s', 'ShellyPlus1PM-...' -> 'Shelly Plus1PM'. */
    fun apName(ssid: String): String {
        val model = ssid.substringBeforeLast("-").drop("shelly".length).trim('-')
        return if (model.isNotEmpty()) "Shelly $model" else "Shelly"
    }

    fun is24(freq: Int) = freq in 1..2999
}

class SetupError(message: String) : Exception(message)

data class WifiNet(val ssid: String, val freq: Int, val signal: Int)

/** The nearby Wi-Fi networks, split into new Shellies and the networks a Shelly could join. */
data class Nearby(val shellies: List<WifiNet>, val homes: List<WifiNet>) {
    /** Heard on 5 GHz only here: the Shelly cannot join it, unless the router has 2.4 GHz under the same name. */
    fun only5(ssid: String) = homes.firstOrNull { it.ssid == ssid }?.let { it.freq > 0 && !ShellySetup.is24(it.freq) } ?: false
}

/** The phone's Wi-Fi, used only while the user sets up a Shelly. */
class PhoneWifi(context: Context) {
    private val ctx = context.applicationContext
    val wifi = ctx.getSystemService(WifiManager::class.java)!!
    private val cm = ctx.getSystemService(ConnectivityManager::class.java)!!

    /** Asks Android for a fresh list (it may refuse when asked too often; then the last list is used). */
    @Suppress("DEPRECATION")
    fun startScan(): Boolean = runCatching { wifi.startScan() }.getOrDefault(false)

    @SuppressLint("MissingPermission")
    fun nearby(): Nearby {
        @Suppress("DEPRECATION")
        val all = runCatching { wifi.scanResults }.getOrDefault(emptyList())
            .mapNotNull { r -> r.SSID?.takeIf { it.isNotBlank() }?.let { WifiNet(it, r.frequency, r.level) } }
        // One entry per name: 2.4 GHz once heard there at all (a Shelly needs it), the strongest signal.
        val merged = all.groupBy { it.ssid }.map { (ssid, nets) ->
            val freq = nets.firstOrNull { ShellySetup.is24(it.freq) }?.freq ?: nets.first().freq
            WifiNet(ssid, freq, nets.maxOf { it.signal })
        }.sortedByDescending { it.signal }
        val (shellies, homes) = merged.partition { ShellySetup.isShellyAp(it.ssid) }
        return Nearby(shellies, homes.sortedBy { !ShellySetup.is24(it.freq) }) // 2.4 GHz first (stable: strongest first)
    }

    /** The name of the Wi-Fi the phone is on, when Android tells it (it needs the location permission for that). */
    suspend fun currentSsid(): String? {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val found = CompletableDeferred<String?>()
            val cb = object : ConnectivityManager.NetworkCallback(FLAG_INCLUDE_LOCATION_INFO) {
                override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                    found.complete(clean((caps.transportInfo as? WifiInfo)?.ssid))
                }
            }
            val req = NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build()
            return try {
                cm.registerNetworkCallback(req, cb)
                withTimeoutOrNull(2000) { found.await() }
            } catch (e: Exception) {
                null
            } finally {
                runCatching { cm.unregisterNetworkCallback(cb) }
            }
        }
        @Suppress("DEPRECATION")
        return clean(runCatching { wifi.connectionInfo?.ssid }.getOrNull())
    }

    private fun clean(ssid: String?): String? =
        ssid?.removeSurrounding("\"")?.takeIf { it.isNotBlank() && it != WifiManager.UNKNOWN_SSID && it != "<unknown ssid>" }

    /**
     * Joins the Shelly's open network for this app only. Android shows its own "connect to device" prompt first.
     * Returns the network and a function that lets go of it again (the phone then goes back to its own Wi-Fi).
     */
    suspend fun join(ssid: String): Pair<Network, () -> Unit> = suspendCancellableCoroutine { cont ->
        val spec = WifiNetworkSpecifier.Builder().setSsid(ssid).build()
        val req = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .setNetworkSpecifier(spec)
            .build()
        lateinit var release: () -> Unit
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                if (cont.isActive) cont.resume(network to release)
            }

            override fun onUnavailable() {
                if (cont.isActive) cont.resumeWithException(SetupError(ShellySetup.OUT_OF_REACH))
            }
        }
        release = { runCatching { cm.unregisterNetworkCallback(cb) } }
        cont.invokeOnCancellation { release() }
        try {
            cm.requestNetwork(req, cb, 60_000) // the user's answer to Android's prompt counts towards this too
        } catch (e: Exception) {
            release()
            if (cont.isActive) cont.resumeWithException(SetupError("Android did not let Noodle join the Shelly's Wi-Fi: ${e.message}"))
        }
    }
}

/** What the Shelly said about itself on its own network. */
data class ShellyAbout(val mac: String, val gen: Int)

/** Talking to the Shelly at 192.168.33.1 over its own network (never over the phone's other networks). */
class ShellyLink(network: Network) {
    private val http = OkHttpClient.Builder()
        .socketFactory(network.socketFactory)
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .build()
    private val base = "http://${ShellySetup.SETUP_ADDRESS}"

    /** `/shelly`, asked again for a while: right after joining, the address may take a few seconds to arrive. */
    suspend fun about(): ShellyAbout = withContext(Dispatchers.IO) {
        val end = System.currentTimeMillis() + ShellySetup.REACH_SECONDS * 1000L
        var body: JsonObject
        while (true) {
            try {
                body = http.newCall(Request.Builder().url("$base/shelly").build()).execute().use { r ->
                    if (!r.isSuccessful) throw IOException("HTTP ${r.code}")
                    json.parseToJsonElement(r.body?.string().orEmpty()).jsonObject
                }
                break
            } catch (e: Exception) {
                if (System.currentTimeMillis() >= end) {
                    throw SetupError("The Shelly did not answer on its own Wi-Fi (${e.javaClass.simpleName})")
                }
                delay(1000)
            }
        }
        val mac = body["mac"]?.jsonPrimitive?.contentOrNull ?: throw SetupError("That network is not a Shelly")
        if (truthy(body["auth"]) || truthy(body["auth_en"])) throw SetupError(ShellySetup.LOCKED)
        ShellyAbout(mac.lowercase().replace(":", ""), body["gen"]?.jsonPrimitive?.intOrNull ?: 1)
    }

    private fun truthy(v: kotlinx.serialization.json.JsonElement?): Boolean {
        val p = v as? JsonPrimitive ?: return false
        return p.content == "true" || (p.intOrNull ?: 0) != 0
    }

    /** Tells the Shelly to join `ssid`. The password only goes into the request body, never a URL or a log line. */
    suspend fun configure(about: ShellyAbout, ssid: String, password: String) = withContext(Dispatchers.IO) {
        if (about.gen >= 2) {
            val body = buildJsonObject {
                put("id", JsonPrimitive(1))
                put("src", JsonPrimitive("noodle"))
                put("method", JsonPrimitive("WiFi.SetConfig"))
                put("params", buildJsonObject {
                    put("config", buildJsonObject {
                        put("sta", buildJsonObject {
                            put("ssid", JsonPrimitive(ssid))
                            put("pass", JsonPrimitive(password))
                            put("enable", JsonPrimitive(true))
                        })
                    })
                })
            }
            val req = Request.Builder().url("$base/rpc").post(body.toString().toRequestBody("application/json".toMediaType())).build()
            http.newCall(req).execute().use { r ->
                if (r.code == 401) throw SetupError(ShellySetup.LOCKED)
                if (!r.isSuccessful) throw SetupError("The Shelly answered HTTP ${r.code}")
                val answer = runCatching { json.parseToJsonElement(r.body?.string().orEmpty()).jsonObject }.getOrNull()
                val error = answer?.get("error")
                if (error != null) {
                    val message = (error as? JsonObject)?.get("message")?.jsonPrimitive?.contentOrNull ?: error.toString()
                    throw SetupError("The Shelly refused the Wi-Fi details: $message")
                }
            }
            return@withContext
        }
        // Gen1: a form POST, so the password is not in a URL.
        val form = FormBody.Builder().add("enabled", "1").add("ssid", ssid)
        if (password.isNotEmpty()) form.add("key", password)
        try {
            http.newCall(Request.Builder().url("$base/settings/sta").post(form.build()).build()).execute().use { r ->
                if (r.code == 401) throw SetupError(ShellySetup.LOCKED)
                if (!r.isSuccessful) throw SetupError("The Shelly answered HTTP ${r.code}")
            }
        } catch (e: IOException) {
            // It may switch networks before it finishes answering: that is fine.
        }
    }
}

/**
 * Finds the Shelly with this MAC on the home network once it announces itself (mDNS), only for as long as the
 * setup waits. Shellies announce themselves with their MAC in the name (`shelly1-A4CF12B3C4D5`,
 * `shellyplus1pm-a8032ab12345`); the match is checked with `/shelly` before it counts.
 */
class ShellyFinder(context: Context) {
    private val nsd = context.applicationContext.getSystemService(NsdManager::class.java)!!
    private val http = OkHttpClient.Builder().connectTimeout(4, TimeUnit.SECONDS).readTimeout(4, TimeUnit.SECONDS).build()

    suspend fun find(mac: String, seconds: Int): String? = withTimeoutOrNull(seconds * 1000L) {
        var host: String? = null
        while (host == null) {
            // Started again every little while: the phone may only just be back on its own Wi-Fi.
            host = withTimeoutOrNull(15_000) { browseOnce(mac) }
        }
        host
    }

    private suspend fun browseOnce(mac: String): String {
        val result = CompletableDeferred<String>()
        val tail = mac.takeLast(6)
        val listeners = listOf("_shelly._tcp.", "_http._tcp.").map { type ->
            object : NsdManager.DiscoveryListener {
                override fun onServiceFound(info: NsdServiceInfo) {
                    if (info.serviceName.lowercase().contains(tail)) resolve(info, mac, result)
                }
                override fun onServiceLost(info: NsdServiceInfo) {}
                override fun onDiscoveryStarted(serviceType: String) {}
                override fun onDiscoveryStopped(serviceType: String) {}
                override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {}
                override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
            }.also { runCatching { nsd.discoverServices(type, NsdManager.PROTOCOL_DNS_SD, it) } }
        }
        try {
            return result.await()
        } finally {
            listeners.forEach { runCatching { nsd.stopServiceDiscovery(it) } }
        }
    }

    @Suppress("DEPRECATION")
    private fun resolve(info: NsdServiceInfo, mac: String, result: CompletableDeferred<String>) {
        runCatching {
            nsd.resolveService(info, object : NsdManager.ResolveListener {
                override fun onResolveFailed(info: NsdServiceInfo, errorCode: Int) {}
                override fun onServiceResolved(info: NsdServiceInfo) {
                    val host = info.host?.hostAddress ?: return
                    if (host.contains(':')) return // the hub adds Shellies by their IPv4 address
                    Thread {
                        if (macAt(host) == mac) result.complete(host)
                    }.start()
                }
            })
        }
    }

    private fun macAt(host: String): String? = runCatching {
        http.newCall(Request.Builder().url("http://$host/shelly").build()).execute().use { r ->
            json.parseToJsonElement(r.body?.string().orEmpty()).jsonObject["mac"]?.jsonPrimitive?.contentOrNull
                ?.lowercase()?.replace(":", "")
        }
    }.getOrNull()
}
