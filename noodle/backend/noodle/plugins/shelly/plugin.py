"""Shelly on the local network (see adapter.py)."""

from .adapter import ShellyAdapter
from ..lan.plugin import LanPlugin


class ShellyPlugin(LanPlugin):
    id = "shelly"
    source = "shelly"
    adapter_class = ShellyAdapter
    name = "Shelly"
    help = ("Shelly relays, plugs, dimmers and lights, controlled directly over your network: no cloud or account. Gen1 and newer (Plus, Pro, Mini) work. Press Search, or add one by its IP address. "
            "Search also finds new Shellies that are not on your Wi-Fi yet and puts them on it.")
    noun = "Shelly plugs and relays"
    search_hint = "A new Shelly only needs power: keep it within reach of this hub's Wi-Fi."
    icon = "plug"
    order = 36
    config_attr = "SHELLY_DEVICES"
    forget = ["shelly_devices"]

    async def add_found(self, adapter, key, **extra):
        await adapter.add_found(key, **extra)  # extra: wifi_ssid, wifi_password, report (a new Shelly, see hotspot.py)


PLUGIN = ShellyPlugin()
