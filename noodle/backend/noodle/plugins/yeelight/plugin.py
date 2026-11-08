"""Yeelight on the local network (see adapter.py)."""

from .adapter import YeelightAdapter
from ..lan.plugin import LanPlugin


class YeelightPlugin(LanPlugin):
    id = "yeelight"
    source = "yeelight"
    adapter_class = YeelightAdapter
    name = "Yeelight"
    help = ("Yeelight bulbs, controlled directly over your network: no cloud. Switch on \"LAN Control\" for each bulb in "
            "the Yeelight app first, then press Search, or add one by its IP address. Not tested on real devices yet.")
    noun = "Yeelight bulbs"
    icon = "bulb"
    order = 38.4
    config_attr = "YEELIGHT_DEVICES"
    forget = ["yeelight_devices"]


PLUGIN = YeelightPlugin()
