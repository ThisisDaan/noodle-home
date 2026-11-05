"""Tasmota, ESPHome, Shelly (MQTT) and other devices that announce themselves over MQTT (adapters/mqttdisc.py)."""

from ..adapters.mqttdisc import MqttAdapter
from .base import Field, Plugin


class MqttDevicesPlugin(Plugin):
    id = "mqtt"
    source = "mqtt"
    adapter_class = MqttAdapter
    name = "MQTT devices"
    help = ("Tasmota, ESPHome and other devices that announce themselves over MQTT (Home Assistant's discovery "
            "format). They use the same broker as Zigbee2MQTT and appear by themselves once they publish. "
            "Switches, lights and sensors are supported.")
    fields = [Field("mqtt_discovery_prefix", "Discovery topic", "homeassistant", advanced=True,
                    help="The topic the devices announce themselves under. Almost always homeassistant.")]
    gated = True
    icon = "plug"
    order = 41
    forget = ["mqtt_discovery_prefix"]

    def status(self, adapter):
        return adapter.client is not None

    def on_remove(self, hub, adapter):
        for device_id in [d.id for d in hub.devices.values() if d.source == "mqtt"]:
            hub.remove(device_id)
        adapter.specs.clear()
        adapter.topics.clear()


PLUGIN = MqttDevicesPlugin()
