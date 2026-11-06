"""Yamaha MusicCast on the local network (see adapter.py)."""

from .adapter import YamahaAdapter
from ..lan.plugin import LanPlugin


class YamahaPlugin(LanPlugin):
    id = "yamaha"
    source = "yamaha"
    adapter_class = YamahaAdapter
    name = "Yamaha MusicCast"
    help = ("Yamaha MusicCast receivers, speakers and soundbars: power, volume and mute, directly, with no account. "
            "Press Search, or add one by its IP address. Not tested on real devices yet.")
    noun = "MusicCast devices"
    icon = "speaker"
    order = 39.4
    config_attr = "YAMAHA_DEVICES"
    forget = ["yamaha_devices"]


PLUGIN = YamahaPlugin()
