package app.noodle

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.BatteryManager
import android.os.CancellationSignal
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume

/** Reports this phone to Noodle as a device: battery, charging and (when allowed) whether it is home. */
class PhoneReportWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val prefs = Prefs(applicationContext)
        if (!prefs.loggedIn || !prefs.reporting) return Result.success()
        val battery = applicationContext.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        val status = battery?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val charging = status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
        val loc = currentLocation(applicationContext)
        val report = PhoneReport(
            id = prefs.phoneId, name = prefs.phoneName,
            battery = if (level >= 0) level * 100 / scale else null, charging = charging,
            latitude = loc?.latitude, longitude = loc?.longitude, accuracy = loc?.accuracy,
        )
        return try {
            Api(prefs).reportPhone(report)
            Result.success()
        } catch (e: ApiException) {
            if (e.code == 401) Result.failure() else Result.retry()
        } catch (e: Exception) {
            Result.retry()
        }
    }

    private suspend fun currentLocation(context: Context): Location? {
        val granted = listOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
            .any { ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED }
        if (!granted) return null
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val provider = listOf(LocationManager.FUSED_PROVIDER, LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER)
            .firstOrNull { runCatching { lm.isProviderEnabled(it) }.getOrDefault(false) } ?: return null
        return try {
            suspendCancellableCoroutine<Location?> { cont ->
                val signal = CancellationSignal()
                cont.invokeOnCancellation { signal.cancel() }
                lm.getCurrentLocation(provider, signal, Executors.newSingleThreadExecutor()) { cont.resume(it) }
            } ?: lm.getLastKnownLocation(provider)
        } catch (e: SecurityException) {
            null
        }
    }

    companion object {
        private val online = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        /** Every 15 minutes (the minimum Android allows for background work) and once right now. */
        fun schedule(context: Context) {
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "phone-report", ExistingPeriodicWorkPolicy.UPDATE,
                PeriodicWorkRequestBuilder<PhoneReportWorker>(15, TimeUnit.MINUTES).setConstraints(online).build(),
            )
            now(context)
        }

        fun now(context: Context) {
            WorkManager.getInstance(context)
                .enqueue(OneTimeWorkRequestBuilder<PhoneReportWorker>().setConstraints(online).build())
        }

        fun cancel(context: Context) = WorkManager.getInstance(context).cancelUniqueWork("phone-report")
    }
}
