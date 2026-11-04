package app.noodle

import android.app.PendingIntent
import android.content.Intent
import android.service.controls.Control
import android.service.controls.ControlsProviderService
import android.service.controls.DeviceTypes
import android.service.controls.actions.BooleanAction
import android.service.controls.actions.ControlAction
import android.service.controls.actions.FloatAction
import android.service.controls.templates.ControlButton
import android.service.controls.templates.RangeTemplate
import android.service.controls.templates.ToggleRangeTemplate
import android.service.controls.templates.ToggleTemplate
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.transform
import kotlinx.coroutines.jdk9.asPublisher
import kotlinx.coroutines.launch
import java.util.concurrent.Flow
import java.util.function.Consumer

/** Noodle in the Android "Device controls" panel (power menu): lights, switches and the thermostat target, live. */
class NoodleControls : ControlsProviderService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private lateinit var api: Api
    private lateinit var live: Live

    override fun onCreate() {
        super.onCreate()
        api = Api(Prefs(this))
        live = Live(api, scope) { }
    }

    override fun onDestroy() {
        live.stop()
        scope.cancel()
        super.onDestroy()
    }

    private fun id(device: Device, entity: Entity) = "${device.id}|${entity.key}"

    private fun controllable(entity: Entity) = entity.kind in setOf("light", "switch", "number")

    private fun intent(): PendingIntent = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun type(entity: Entity) = when (entity.kind) {
        "light" -> DeviceTypes.TYPE_LIGHT
        "number" -> DeviceTypes.TYPE_THERMOSTAT
        else -> DeviceTypes.TYPE_SWITCH
    }

    private fun title(device: Device, entity: Entity) =
        if (device.entities.count { controllable(it) } > 1) "${device.name} · ${entity.name}" else device.name

    override fun createPublisherForAllAvailable(): Flow.Publisher<Control> = flow {
        if (!Prefs(this@NoodleControls).loggedIn) return@flow
        val devices = runCatching { api.devices() }.getOrDefault(emptyList())
        for (d in devices) for (e in d.entities.filter { controllable(it) }) {
            emit(
                Control.StatelessBuilder(id(d, e), intent())
                    .setTitle(title(d, e)).setZone(d.area ?: "Other").setDeviceType(type(e)).build(),
            )
        }
    }.asPublisher()

    override fun createPublisherFor(controlIds: List<String>): Flow.Publisher<Control> {
        live.start()
        android.util.Log.i("Noodle", "controls subscribe: $controlIds")
        return live.devices.transform { devices ->
            for (controlId in controlIds) {
                val (deviceId, key) = controlId.split("|", limit = 2).let { it[0] to it.getOrElse(1) { "" } }
                val device = devices[deviceId] ?: run { android.util.Log.w("Noodle", "no device $deviceId"); null } ?: continue
                val entity = device.entities.firstOrNull { it.key == key } ?: continue
                emit(build(controlId, device, entity))
            }
        }.asPublisher()
    }

    private fun build(controlId: String, device: Device, entity: Entity): Control {
        val b = Control.StatefulBuilder(controlId, intent())
            .setTitle(title(device, entity))
            .setZone(device.area ?: "Other")
            .setDeviceType(type(entity))
            .setStatus(if (device.available) Control.STATUS_OK else Control.STATUS_DISABLED)
        when {
            entity.kind == "number" -> {
                val value = (entity.number ?: 18.0).toFloat()
                b.setStatusText(entity.text)
                b.setControlTemplate(RangeTemplate(controlId, 10f, 24f, value.coerceIn(10f, 24f), 0.5f, "%.1f"))
            }
            entity.kind == "light" && entity.brightness != null -> {
                val on = entity.on == true
                b.setStatusText(if (on) "${entity.brightness}%" else "Off")
                b.setControlTemplate(
                    ToggleRangeTemplate(controlId, on, "",
                        RangeTemplate(controlId, 1f, 100f, entity.brightness.toFloat().coerceIn(1f, 100f), 1f, "%.0f%%")),
                )
            }
            else -> {
                val on = entity.on == true
                b.setStatusText(if (on) "On" else "Off")
                b.setControlTemplate(ToggleTemplate(controlId, ControlButton(on, "")))
            }
        }
        return b.build()
    }

    override fun performControlAction(controlId: String, action: ControlAction, consumer: Consumer<Int>) {
        val (deviceId, key) = controlId.split("|", limit = 2).let { it[0] to it.getOrElse(1) { "" } }
        scope.launch {
            val result = try {
                when (action) {
                    is BooleanAction -> api.command(deviceId, key, on = action.newState)
                    is FloatAction -> {
                        val entity = live.devices.value[deviceId]?.entities?.firstOrNull { it.key == key }
                        if (entity?.kind == "number") api.command(deviceId, key, value = action.newValue.toDouble())
                        else api.command(deviceId, key, on = true, brightness = action.newValue.toInt())
                    }
                    else -> Unit
                }
                ControlAction.RESPONSE_OK
            } catch (e: Exception) {
                ControlAction.RESPONSE_FAIL
            }
            consumer.accept(result)
        }
    }
}
