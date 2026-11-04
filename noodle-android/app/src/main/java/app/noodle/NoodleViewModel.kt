package app.noodle

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class NoodleViewModel(app: Application) : AndroidViewModel(app) {
    val prefs = Prefs(app)
    private val api = Api(prefs)
    private val _loggedIn = MutableStateFlow(prefs.loggedIn)
    private val _error = MutableStateFlow<String?>(null)
    private val _busy = MutableStateFlow(false)
    val loggedIn: StateFlow<Boolean> = _loggedIn
    val error: StateFlow<String?> = _error
    val busy: StateFlow<Boolean> = _busy


    fun login(url: String, password: String, phoneName: String) {
        viewModelScope.launch {
            _busy.value = true
            _error.value = null
            try {
                prefs.phoneName = phoneName.ifBlank { prefs.phoneName }
                prefs.token = api.login(url, password, "Android: ${prefs.phoneName}")
                _loggedIn.value = true
                if (prefs.reporting) PhoneReportWorker.schedule(getApplication())
                NotifyService.sync(getApplication())
            } catch (e: Exception) {
                _error.value = e.message ?: "Login failed"
            } finally {
                _busy.value = false
            }
        }
    }

    fun logout() {
        NotifyService.stop(getApplication())
        prefs.logout()
        android.webkit.CookieManager.getInstance().removeAllCookies(null)
        PhoneReportWorker.cancel(getApplication())
        _loggedIn.value = false
    }

    fun dismissError() { _error.value = null }

    fun setReporting(on: Boolean) {
        prefs.reporting = on
        if (on) PhoneReportWorker.schedule(getApplication()) else PhoneReportWorker.cancel(getApplication())
    }

    fun setNotifications(on: Boolean) {
        prefs.notifications = on
        NotifyService.sync(getApplication())
    }

    fun reportNow() = PhoneReportWorker.now(getApplication())
}
