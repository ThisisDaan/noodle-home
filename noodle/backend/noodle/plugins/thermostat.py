"""A thermostat device: a room temperature sensor and a heater plug, picked on the Integrations page."""

from .. import config
from ..adapters.thermostat import ThermostatAdapter
from .base import Field, Plugin


class ThermostatPlugin(Plugin):
    id = "thermostat"
    source = "thermostat"
    adapter_class = ThermostatAdapter
    name = "Thermostat"
    help = ("Keeps a room at a target temperature: it switches a heater plug on and off from a room temperature "
            "sensor. Pick the sensor and the plug; the thermostat then shows up as a device.")
    fields = [Field("thermostat_name", "Name", "Living room heating"),
              Field("thermostat_sensor_device", "Room sensor (device)"), Field("thermostat_sensor_key", "Room sensor (reading)"),
              Field("thermostat_heater_device", "Heater plug (device)"), Field("thermostat_heater_key", "Heater plug (switch)")]
    gated = True
    icon = "thermo"
    panel = "thermostat"
    custom_form = True
    forget = [f.key for f in fields]
    order = 25

    def status(self, adapter):
        if not adapter.configured:
            return None
        return adapter.device_id in adapter.hub.devices

    def preset(self):
        return bool(config.THERMOSTAT_SENSOR_DEVICE and config.THERMOSTAT_HEATER_DEVICE)

    def on_remove(self, hub, adapter):
        adapter.remove()


PLUGIN = ThermostatPlugin()
