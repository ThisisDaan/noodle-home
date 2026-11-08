"""Pi-hole on the local network (see adapter.py)."""

from ... import config
from .adapter import PiholeAdapter
from ..base import Field, Plugin


class PiholePlugin(Plugin):
    id = "pihole"
    source = "pihole"
    adapter_class = PiholeAdapter
    name = "Pi-hole"
    help = ("Switch Pi-hole's ad blocking on and off and see how many queries it blocked today. Needs Pi-hole 6 or "
            "later. Use the password of its web interface (or make an app password in its settings). Not tested on "
            "a real Pi-hole yet.")
    fields = [Field("pihole_url", "Pi-hole address", "http://pi.hole"),
              Field("pihole_password", "Password", secret=True)]
    gated = True
    icon = "wifi"
    order = 44
    forget = ["pihole_url", "pihole_password"]

    def details(self, adapter):
        return {"error": adapter.error}

    def preset(self):
        return bool(config.PIHOLE_URL)

    def on_remove(self, hub, adapter):
        super().on_remove(hub, adapter)
        adapter.connected = False
        adapter._sid = None


PLUGIN = PiholePlugin()
