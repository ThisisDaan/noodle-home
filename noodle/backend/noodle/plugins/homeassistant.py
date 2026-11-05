"""Home Assistant as a source of devices (adapters/homeassistant.py)."""

from ..adapters.homeassistant import HomeAssistantAdapter
from .base import Field, Plugin


class HomeAssistantPlugin(Plugin):
    id = "homeassistant"
    source = "homeassistant"
    adapter_class = HomeAssistantAdapter
    name = "Home Assistant"
    help = ("Bring in the lights, switches, fans, blinds, locks and sensors your Home Assistant controls, for "
            "everything Noodle has no integration of its own for. Make a token on your Home Assistant profile page "
            "(Security, Long-lived access tokens). A device that is also paired with Noodle directly would show up twice.")
    fields = [Field("ha_url", "Address", "http://homeassistant.local:8123"),
              Field("ha_token", "Long-lived access token", secret=True)]
    gated = True
    icon = "home"
    order = 42
    forget = ["ha_url", "ha_token"]

    def status(self, adapter):
        if adapter.connected:
            return True
        return False if adapter.error else None

    def details(self, adapter):
        return {"error": adapter.error}

    def preset(self):
        from .. import config
        return bool(config.HA_URL and config.HA_TOKEN)

    def on_remove(self, hub, adapter):
        for device_id in [d.id for d in hub.devices.values() if d.source == "homeassistant"]:
            hub.remove(device_id)
        adapter.entity_device.clear()


PLUGIN = HomeAssistantPlugin()
