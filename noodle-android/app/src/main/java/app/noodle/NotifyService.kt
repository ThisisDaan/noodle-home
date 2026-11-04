package app.noodle

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Local notifications: keeps a connection to Noodle on the home network open and shows what the Pi sends as normal
 * Android notifications (with their buttons). It needs no internet and no Google push service, but only works while
 * the phone can reach the Pi (home Wi-Fi, or a VPN). Android requires the small "connected" notification.
 */
class NotifyService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var live: Live? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val prefs = Prefs(this)
        if (!prefs.loggedIn || !prefs.notifications) {
            stopSelf()
            return START_NOT_STICKY
        }
        createChannels(this)
        val ongoing = NotificationCompat.Builder(this, CHANNEL_STATUS)
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentTitle("Noodle")
            .setContentText("Listening for notifications on your home network")
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setContentIntent(openApp(this))
            .build()
        startForeground(STATUS_ID, ongoing, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        if (live == null) {
            // Away from home the Pi cannot be reached: try again only about once a minute, to spare the battery.
            live = Live(Api(prefs), scope, maxPause = 60_000L, onNotification = { show(it) }) { stopSelf() }.also { it.start() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        live?.stop()
        scope.cancel()
        super.onDestroy()
    }

    private fun show(msg: JsonObject) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val id = msg["id"]?.jsonPrimitive?.content ?: System.nanoTime().toString()
        val priority = msg["priority"]?.jsonPrimitive?.content ?: "default"
        val notificationId = id.hashCode()
        val builder = NotificationCompat.Builder(this, channelFor(priority))
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentTitle(msg["title"]?.jsonPrimitive?.content ?: "Noodle")
            .setContentText(msg["message"]?.jsonPrimitive?.content ?: "")
            .setStyle(NotificationCompat.BigTextStyle().bigText(msg["message"]?.jsonPrimitive?.content ?: ""))
            .setAutoCancel(true)
            .setContentIntent(openApp(this))
        val base = Prefs(this).baseUrl
        (msg["buttons"] as? JsonArray ?: JsonArray(emptyList())).take(3).forEachIndexed { i, b ->
            val button = b.jsonObject
            val label = button["label"]?.jsonPrimitive?.content ?: return@forEachIndexed
            var url = button["url"]?.jsonPrimitive?.content ?: return@forEachIndexed
            if (url.startsWith("/")) url = base + url // the Pi does not know its own address when it is not configured
            val tap = Intent(this, ActionReceiver::class.java)
                .putExtra("url", url).putExtra("notification", notificationId)
                .setAction("noodle.action.$id.$i")
            builder.addAction(0, label, PendingIntent.getBroadcast(this, 0, tap, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
        }
        getSystemService(NotificationManager::class.java).notify(notificationId, builder.build())
    }

    companion object {
        private const val CHANNEL_STATUS = "status"
        private const val STATUS_ID = 1

        private fun channelFor(priority: String) = when (priority) {
            "low" -> "alerts_low"
            "high", "urgent" -> "alerts_high"
            else -> "alerts_default"
        }

        private fun createChannels(context: Context) {
            val nm = context.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel(CHANNEL_STATUS, "Connection", NotificationManager.IMPORTANCE_MIN)
                .apply { description = "The small notification that keeps Noodle listening on your home network" })
            nm.createNotificationChannel(NotificationChannel("alerts_low", "Quiet notifications", NotificationManager.IMPORTANCE_LOW))
            nm.createNotificationChannel(NotificationChannel("alerts_default", "Notifications", NotificationManager.IMPORTANCE_DEFAULT))
            nm.createNotificationChannel(NotificationChannel("alerts_high", "Important notifications", NotificationManager.IMPORTANCE_HIGH))
        }

        private fun openApp(context: Context): PendingIntent = PendingIntent.getActivity(
            context, 0, Intent(context, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        /** Starts or stops the service to match the settings. Call it while the app is on screen, or from boot. */
        fun sync(context: Context) {
            val prefs = Prefs(context)
            if (prefs.loggedIn && prefs.notifications) {
                try {
                    ContextCompat.startForegroundService(context, Intent(context, NotifyService::class.java))
                } catch (e: Exception) {
                    // Not allowed right now (app in the background): it will start the next time the app opens.
                }
            } else {
                stop(context)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, NotifyService::class.java))
        }
    }
}

/** A notification button was tapped: send its request to the Pi, then dismiss the notification. */
class ActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val url = intent.getStringExtra("url") ?: return
        val notificationId = intent.getIntExtra("notification", 0)
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val api = Api(Prefs(context))
                api.client.newCall(Request.Builder().url(url).post("".toRequestBody()).build()).execute().close()
            } catch (e: Exception) {
                // The Pi could not be reached; the notification stays so it can be tried again.
                pending.finish()
                return@launch
            }
            context.getSystemService(NotificationManager::class.java).cancel(notificationId)
            pending.finish()
        }
    }
}

/** Starts listening again after the phone restarts. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) NotifyService.sync(context)
    }
}
