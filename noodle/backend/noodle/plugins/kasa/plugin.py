"""TP-Link Kasa on the local network (see adapter.py)."""

from .adapter import KasaAdapter
from ..lan.plugin import LanPlugin


class KasaPlugin(LanPlugin):
    id = "kasa"
    source = "kasa"
    adapter_class = KasaAdapter
    name = "TP-Link Kasa"
    help = ("TP-Link Kasa plugs and bulbs, controlled directly: no cloud or account. (Tapo devices use a different protocol and are not supported.) Press Search, or add one by its IP address.")
    noun = "Kasa devices"
    icon = "plug"
    order = 38
    config_attr = "KASA_DEVICES"
    forget = ["kasa_devices"]


PLUGIN = KasaPlugin()
