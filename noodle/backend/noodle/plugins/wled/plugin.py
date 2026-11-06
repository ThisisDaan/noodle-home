"""WLED on the local network (see adapter.py)."""

from .adapter import WledAdapter
from ..lan.plugin import LanPlugin


class WledPlugin(LanPlugin):
    id = "wled"
    source = "wled"
    adapter_class = WledAdapter
    name = "WLED"
    help = ("WLED LED strips on your network, controlled directly. Press Search, or add one by its IP address.")
    noun = "WLED strips"
    icon = "bulb"
    order = 37
    config_attr = "WLED_DEVICES"
    forget = ["wled_devices"]


PLUGIN = WledPlugin()
