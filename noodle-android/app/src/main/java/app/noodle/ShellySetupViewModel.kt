package app.noodle

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** The "Set up a new Shelly" screen. Lives as long as the screen, so a setup that is under way survives a rotation. */
class ShellySetupViewModel(app: Application) : AndroidViewModel(app) {
    private val wifi = PhoneWifi(app)
    private val api = Api(Prefs(app))

    data class State(
        val nearby: Nearby = Nearby(emptyList(), emptyList()),
        val looked: Boolean = false, // a list has come in since the screen opened
        val current: String? = null, // the Wi-Fi the phone is on, when Android says
        val step: String? = null, // what the setup is doing now
        val error: String? = null,
        val done: String? = null,
    ) {
        val busy get() = step != null
    }

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state
    private var job: Job? = null

    /** Asks for a fresh list; the result comes in through [readNearby] when Android has it. */
    fun search() {
        if (!wifi.startScan()) readNearby() // refused (asked too often): use what Android heard last
        viewModelScope.launch { wifi.currentSsid()?.let { ssid -> _state.value = _state.value.copy(current = ssid) } }
    }

    fun readNearby() {
        _state.value = _state.value.copy(nearby = wifi.nearby(), looked = true)
    }

    fun dismiss() {
        _state.value = _state.value.copy(error = null, done = null)
    }

    /** The password is only passed through to the Shelly: it is not kept here or anywhere else. */
    fun setUp(shellySsid: String, homeSsid: String, password: String) {
        if (job?.isActive == true) return
        job = viewModelScope.launch {
            fun step(text: String) { _state.value = _state.value.copy(step = text, error = null, done = null) }
            try {
                step("Joining the Shelly's own Wi-Fi…")
                val (network, release) = wifi.join(shellySsid)
                val about = try {
                    val link = ShellyLink(network)
                    val about = link.about()
                    step("Giving it your Wi-Fi details…")
                    link.configure(about, homeSsid, password)
                    about
                } finally {
                    step("Going back to your network…")
                    release()
                }
                step("Waiting for it to join $homeSsid…")
                val host = ShellyFinder(getApplication()).find(about.mac, ShellySetup.JOIN_SECONDS)
                if (host == null) {
                    throw SetupError("The Shelly did not show up on $homeSsid. Check the password and that $homeSsid is a " +
                        "2.4 GHz network, then reset the Shelly (hold its button for about 10 seconds) and search again. " +
                        "If it is there after all, press Search in Noodle to add it.")
                }
                step("Adding it…")
                try {
                    api.addShelly(host)
                } catch (e: Exception) {
                    throw SetupError("The Shelly is on $homeSsid at $host, but Noodle could not add it (${e.message}). " +
                        "Press Search in Noodle to add it.")
                }
                _state.value = _state.value.copy(step = null, done = "${ShellySetup.apName(shellySsid)} is on $homeSsid and added to Noodle.",
                    nearby = _state.value.nearby.copy(shellies = _state.value.nearby.shellies.filter { it.ssid != shellySsid }))
            } catch (e: SetupError) {
                _state.value = _state.value.copy(step = null, error = e.message)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.value = _state.value.copy(step = null, error = e.message ?: e.javaClass.simpleName)
            }
        }
    }
}
