package app.noodle

import android.content.Context
import android.os.Build
import java.util.UUID

/** Everything the app remembers: where the server is, the login token and the phone's own identity. */
class Prefs(context: Context) {
    private val p = context.getSharedPreferences("noodle", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = p.getString("url", "") ?: ""
        set(v) = p.edit().putString("url", normalize(v)).apply()
    var token: String
        get() = p.getString("token", "") ?: ""
        set(v) = p.edit().putString("token", v).apply()
    var phoneName: String
        get() = p.getString("phone_name", null) ?: Build.MODEL
        set(v) = p.edit().putString("phone_name", v).apply()
    var reporting: Boolean
        get() = p.getBoolean("reporting", true)
        set(v) = p.edit().putBoolean("reporting", v).apply()
    var notifications: Boolean
        get() = p.getBoolean("notifications", true)
        set(v) = p.edit().putBoolean("notifications", v).apply()
    val phoneId: String
        get() = p.getString("phone_id", null) ?: UUID.randomUUID().toString().also { p.edit().putString("phone_id", it).apply() }

    val loggedIn get() = token.isNotEmpty() && baseUrl.isNotEmpty()

    fun logout() = p.edit().remove("token").apply()

    companion object {
        fun normalize(raw: String): String {
            var u = raw.trim().trimEnd('/')
            if (u.isNotEmpty() && !u.startsWith("http://") && !u.startsWith("https://")) u = "http://$u"
            return u
        }
    }
}
