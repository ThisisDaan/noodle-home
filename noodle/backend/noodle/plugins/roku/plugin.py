"""Roku on the local network (see adapter.py)."""

from .adapter import RokuAdapter
from ..lan.plugin import LanPlugin


class RokuPlugin(LanPlugin):
    id = "roku"
    source = "roku"
    adapter_class = RokuAdapter
    name = "Roku"
    help = ("Roku players and TVs on your network: power, play and pause, and which app is open, with no account. "
            "Press Search, or add one by its IP address. If commands do nothing, set Settings, System, Advanced system "
            "settings, External control to Enabled on the Roku. Not tested on real devices yet.")
    noun = "Roku devices"
    icon = "speaker"
    order = 39.2
    config_attr = "ROKU_DEVICES"
    forget = ["roku_devices"]


PLUGIN = RokuPlugin()
