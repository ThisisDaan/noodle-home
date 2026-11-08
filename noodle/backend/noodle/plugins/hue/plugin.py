"""Philips Hue bridges. There can be several; each is paired once and its lights, switches and sensors join the hub."""

from fastapi import APIRouter, Depends, HTTPException

from ... import config
from . import adapter as hue_adapter
from .adapter import HueAdapter
from ..base import Field, Plugin, PressButton


def clean_host(text: str) -> str:
    return text.strip().removeprefix("https://").removeprefix("http://").rstrip("/")


class HuePlugin(Plugin):
    id = "hue"
    source = "hue"
    adapter_class = HueAdapter
    name = "Philips Hue"
    help = ("Connects to your Hue bridges so their lights, switches and sensors show up here. Search for a bridge, "
            "then press the round button on top of it when asked. You can add more than one bridge.")
    # The bridges are listed and paired by the panel, not typed into a form.
    fields = [Field("hue_host", "Hue bridge address", "192.168.1.20", hidden=True),
              Field("hue_key", "Application key", secret=True, hidden=True),
              Field("hue_bridges", "Bridges", secret=True, hidden=True)]
    support = "supported"
    panel = "hue"
    icon = "bulb"
    forget = ["hue_host", "hue_key", "hue_bridges"]
    order = 30
    searchable = True
    search_finds = "connection"  # a bridge; its lights and sensors join by themselves
    noun = "Hue bridges"
    press_hint = "Press the round button on top of your Hue bridge."
    restart_after_add = True

    def status(self, adapter):
        return adapter.connected if config.hue_bridges() else None

    def preset(self):
        return bool(config.HUE_HOST or config.HUE_BRIDGES)  # a bridge that was set up before counts as added

    def details(self, adapter):
        return {"bridges": [{"host": host, "connected": bool(adapter.state.get(host, {}).get("connected")),
                             "error": adapter.state.get(host, {}).get("error")} for host in config.hue_bridges()]}

    async def search(self, adapter, seconds, found):
        known = set(config.hue_bridges())
        seen: set[str] = set()

        def offer(host: str) -> None:
            if host not in known and host not in seen:  # the ones that are already paired are not offered again
                seen.add(host)
                found(host, name="Hue bridge", detail=host)

        await hue_adapter.discover(seconds, offer)

    async def add_found(self, adapter, key):
        host = clean_host(key)
        if host in config.hue_bridges():
            raise ValueError("That bridge is already added")
        try:
            hue_key = await hue_adapter.pair(host)
        except hue_adapter.ButtonNotPressed as err:
            raise PressButton(str(err))
        except ValueError:
            raise
        except Exception as err:
            raise ValueError(f"Could not reach the bridge at {host}: {err}")
        config.save({"hue_bridges": {**config.HUE_BRIDGES, host: hue_key}})

    def on_remove(self, hub, adapter):
        for host in list(adapter.devices_of):  # the settings are cleared by `forget`
            adapter.forget_bridge(host)

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.delete("/api/hue/bridges/{host}")
        async def forget(host: str) -> dict:
            """Remove one bridge (and its devices); the others stay."""
            host = clean_host(host)
            if host not in config.hue_bridges():
                raise HTTPException(404, "That bridge is not added")
            if config.HUE_HOST == host:  # the one from before there could be several
                config.save({"hue_host": "", "hue_key": ""})
            config.save({"hue_bridges": {h: k for h, k in config.HUE_BRIDGES.items() if h != host}})
            adapter.forget_bridge(host)
            await ctx.restart_adapter("hue")
            return ctx.describe("hue")

        return router


PLUGIN = HuePlugin()
