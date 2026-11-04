"""LIFX bulbs on the local network."""

from .. import config
from ..adapters.lifx import LifxAdapter
from .base import Field, Plugin


class LifxPlugin(Plugin):
    id = "lifx"
    source = "lifx"
    adapter_class = LifxAdapter
    name = "LIFX"
    help = ("LIFX bulbs on your network, controlled directly: no cloud, account or bridge. They are found "
            "automatically. If yours are on another network or VLAN, add their addresses.")
    fields = [Field("lifx_hosts", "Extra bulb addresses (optional)", "192.168.1.40, 192.168.1.41")]
    gated = True
    icon = "bulb"
    forget = ["lifx_hosts"]
    order = 35

    def status(self, adapter):
        return True if any(b.heard for b in adapter.bulbs.values()) else (False if adapter.running else None)

    def preset(self):
        return bool(config.LIFX_HOSTS)

    def on_remove(self, hub, adapter):
        for device_id in [d.id for d in hub.devices.values() if d.source == "lifx"]:
            hub.remove(device_id)
        adapter.bulbs.clear()


PLUGIN = LifxPlugin()
