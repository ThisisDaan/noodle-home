"""Govee lights on the local network (see adapter.py)."""

from .adapter import GoveeAdapter
from ..lan.plugin import LanPlugin


class GoveePlugin(LanPlugin):
    id = "govee"
    source = "govee"
    adapter_class = GoveeAdapter
    name = "Govee"
    help = ("Govee lights, controlled directly over your network: no cloud. Only models with LAN control work; switch "
            "it on for each light in the Govee Home app first, then press Search, or add one by its IP address. "
            "Not tested on real devices yet.")
    noun = "Govee lights"
    icon = "bulb"
    order = 38.6
    config_attr = "GOVEE_DEVICES"
    forget = ["govee_devices"]


PLUGIN = GoveePlugin()
