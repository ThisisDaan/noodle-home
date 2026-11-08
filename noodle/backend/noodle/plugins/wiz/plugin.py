"""Philips WiZ on the local network (see adapter.py)."""

from .adapter import WizAdapter
from ..lan.plugin import LanPlugin


class WizPlugin(LanPlugin):
    id = "wiz"
    source = "wiz"
    adapter_class = WizAdapter
    name = "Philips WiZ"
    help = ("Philips WiZ bulbs and plugs, controlled directly over your network: no cloud or account. Set the bulb up "
            "once in the WiZ app, then press Search here, or add one by its IP address. Not tested on real devices yet.")
    noun = "WiZ devices"
    icon = "bulb"
    order = 38.2
    config_attr = "WIZ_DEVICES"
    forget = ["wiz_devices"]


PLUGIN = WizPlugin()
