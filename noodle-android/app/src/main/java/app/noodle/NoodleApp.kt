package app.noodle

import android.app.Application

class NoodleApp : Application() {
    override fun onCreate() {
        super.onCreate()
        val prefs = Prefs(this)
        if (prefs.loggedIn && prefs.reporting) PhoneReportWorker.schedule(this)
    }
}
