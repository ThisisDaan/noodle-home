"""Shelly on the local network (see adapters/shelly.py)."""

from ..adapters.shelly import ShellyAdapter
from .lan import LanPlugin


class ShellyPlugin(LanPlugin):
    id = "shelly"
    source = "shelly"
    adapter_class = ShellyAdapter
    name = "Shelly"
    help = ("Shelly relays, plugs, dimmers and lights, controlled directly over your network: no cloud or account. Gen1 and newer (Plus, Pro, Mini) work. Press Search, or add one by its IP address.")
    noun = "Shelly plugs and relays"
    icon = "plug"
    order = 36
    config_attr = "SHELLY_DEVICES"
    forget = ["shelly_devices"]


PLUGIN = ShellyPlugin()
