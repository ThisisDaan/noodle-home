"""Nanoleaf light panels on the local network (see adapter.py)."""

from .adapter import NanoleafAdapter
from ..lan.plugin import LanPlugin


class NanoleafPlugin(LanPlugin):
    id = "nanoleaf"
    source = "nanoleaf"
    adapter_class = NanoleafAdapter
    name = "Nanoleaf"
    help = ("Nanoleaf panels, Canvas and Shapes, controlled directly: no cloud or account. To add one, hold its "
            "power button for 5-7 seconds until the lights flash, then press Search (or add it by its IP address).")
    noun = "Nanoleaf panels"
    search_hint = "Hold the power button for 5-7 seconds until the lights flash, then add it here within 30 seconds."
    press_hint = "Hold the power button of the Nanoleaf for 5-7 seconds until the lights flash."
    icon = "bulb"
    order = 40
    config_attr = "NANOLEAF_DEVICES"
    forget = ["nanoleaf_devices", "nanoleaf_tokens"]


PLUGIN = NanoleafPlugin()
