"""A thermostat device: a room temperature sensor and a heater plug, picked on the Integrations page."""

import logging

from .. import config
from ..adapters.thermostat import ThermostatAdapter
from .base import Field, Plugin

log = logging.getLogger(__name__)


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


def migrate_from_fixed_devices(store) -> None:
    """One time, for the install this hub was first written for: the thermostat used to be fixed to one sensor and
    one plug in the code. Write those into the settings so it keeps working. Delete this once that hub has upgraded."""
    mac = "4C:65:A8:DC:94:84"
    if config.THERMOSTAT_SENSOR_DEVICE or not (store.get("thermostat_mode") is not None or mac in config.BLE_SENSORS):
        return
    values = {"thermostat_id": "thermostat:woonkamer", "thermostat_name": "Verwarming woonkamer",
              "thermostat_sensor_device": f"ble:{mac}", "thermostat_sensor_key": "temperature",
              "thermostat_heater_device": "zigbee:0xa4c1386c2b42034c", "thermostat_heater_key": "switch"}
    if config.INTEGRATIONS and PLUGIN.id not in config.INTEGRATIONS:  # the user already picks what to add
        values["integrations"] = ",".join([*config.INTEGRATIONS, PLUGIN.id])
    config.save(values)
    log.info("thermostat settings written from the fixed devices it used before")
