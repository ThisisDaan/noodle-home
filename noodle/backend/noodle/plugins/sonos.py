"""Sonos on the local network (see adapters/sonos.py)."""

from ..adapters.sonos import SonosAdapter
from .lan import LanPlugin


class SonosPlugin(LanPlugin):
    id = "sonos"
    source = "sonos"
    adapter_class = SonosAdapter
    name = "Sonos"
    help = ("Sonos speakers on your network: play, pause, volume and mute, directly, with no account. Press Search, or add one by its IP address.")
    noun = "Sonos speakers"
    icon = "speaker"
    order = 39
    config_attr = "SONOS_DEVICES"
    forget = ["sonos_devices"]


PLUGIN = SonosPlugin()
