"""UniFi presence (see adapter.py)."""

from ... import config
from .adapter import UnifiAdapter
from ..base import Field, Plugin


class UnifiPlugin(Plugin):
    id = "unifi"
    source = "unifi"
    adapter_class = UnifiAdapter
    name = "UniFi presence"
    help = ("Know who is home from your own UniFi controller: a device counts as home while it is on your Wi-Fi. "
            "List the devices to follow as MAC=Name pairs, like aa:bb:cc:dd:ee:ff=Anna's phone. Use a local account "
            "of the controller (a read-only one is enough). Not tested on a real controller yet.")
    fields = [Field("unifi_url", "Controller address", "https://192.168.1.2:8443"),
              Field("unifi_username", "Username", "readonly"),
              Field("unifi_password", "Password", secret=True),
              Field("unifi_devices", "Devices to follow", "aa:bb:cc:dd:ee:ff=Anna's phone, 11:22:33:44:55:66=Ben's phone"),
              Field("unifi_site", "Site", "default", advanced=True)]
    gated = True
    icon = "wifi"
    order = 45
    forget = ["unifi_url", "unifi_username", "unifi_password", "unifi_devices"]

    def details(self, adapter):
        return {"error": adapter.error}

    def preset(self):
        return bool(config.UNIFI_URL and config.UNIFI_USERNAME)

    def on_remove(self, hub, adapter):
        super().on_remove(hub, adapter)
        adapter.connected = False
        adapter._logged_in = False
        adapter._seen.clear()


PLUGIN = UnifiPlugin()
