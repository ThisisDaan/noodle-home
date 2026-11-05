"""Philips Hue bridge."""

from .. import config
from ..adapters import hue as hue_adapter
from ..adapters.hue import HueAdapter
from .base import Field, Plugin, PressButton


class HuePlugin(Plugin):
    id = "hue"
    source = "hue"
    adapter_class = HueAdapter
    name = "Philips Hue"
    help = ("Connects to your Hue bridge so its lights, switches and sensors show up here. Search for the bridge, "
            "then press the round button on top of it when asked.")
    fields = [Field("hue_host", "Hue bridge address", "192.168.1.20"),
              Field("hue_key", "Application key", "filled in by pairing", secret=True)]
    icon = "bulb"
    forget = ["hue_host", "hue_key"]
    order = 30
    searchable = True
    noun = "Hue bridges"
    press_hint = "Press the round button on top of your Hue bridge."
    restart_after_add = True

    def status(self, adapter):
        return adapter.connected if config.HUE_HOST and config.HUE_KEY else None

    def preset(self):
        return bool(config.HUE_HOST)

    async def search(self, adapter, seconds, found):
        for host in await hue_adapter.discover():
            found(host, name="Hue bridge", detail=host)

    async def add_found(self, adapter, key):
        host = key.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        try:
            hue_key = await hue_adapter.pair(host)
        except hue_adapter.ButtonNotPressed as err:
            raise PressButton(str(err))
        except ValueError:
            raise
        except Exception as err:
            raise ValueError(f"Could not reach the bridge at {host}: {err}")
        config.save({"hue_host": host, "hue_key": hue_key})


PLUGIN = HuePlugin()
