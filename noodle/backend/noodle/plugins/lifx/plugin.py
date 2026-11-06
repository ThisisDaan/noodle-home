"""LIFX bulbs on the local network."""

from fastapi import APIRouter, Depends

from ... import config
from .adapter import LifxAdapter
from ..base import Field, Plugin


class LifxPlugin(Plugin):
    id = "lifx"
    source = "lifx"
    adapter_class = LifxAdapter
    name = "LIFX"
    help = ("LIFX bulbs on your network, controlled directly: no cloud, account or bridge. The bulbs must be on "
            "your Wi-Fi already (set up in the LIFX app). Press Search to find them.")
    fields = [Field("lifx_hosts", "Extra addresses to search (optional)", "192.168.1.40, 192.168.1.41")]
    gated = True
    searchable = True
    noun = "LIFX bulbs"
    restart_after_add = False
    icon = "bulb"
    panel = "lifx"
    forget = ["lifx_hosts", "lifx_bulbs"]
    order = 35

    def status(self, adapter):
        if any(b.heard for b in adapter.bulbs.values()):
            return True
        return False if adapter.bulbs else None

    def preset(self):
        return bool(config.LIFX_BULBS)

    def details(self, adapter):
        return {"bulbs": adapter.bulb_list()}

    def on_remove(self, hub, adapter):
        super().on_remove(hub, adapter)
        adapter.bulbs.clear()
        adapter.nearby.clear()

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.delete("/api/lifx/bulbs/{mac}")
        async def lifx_forget(mac: str) -> dict:
            adapter.forget(mac)
            return ctx.describe("lifx")

        return router


PLUGIN = LifxPlugin()
