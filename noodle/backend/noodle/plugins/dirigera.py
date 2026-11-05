"""IKEA DIRIGERA hub (adapters/dirigera.py)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import config
from ..adapters.dirigera import DirigeraAdapter
from .base import Field, Plugin


class PairBody(BaseModel):
    host: str


class DirigeraPlugin(Plugin):
    id = "dirigera"
    source = "dirigera"
    adapter_class = DirigeraAdapter
    name = "IKEA DIRIGERA"
    help = ("Lights, outlets, blinds and sensors on your IKEA DIRIGERA hub, controlled over your network: no cloud. "
            "Enter the hub's IP address, press Connect, then press the action button on the hub and press Connect again.")
    fields = [Field("dirigera_host", "Hub address", hidden=True), Field("dirigera_token", "Token", secret=True, hidden=True)]
    gated = True
    panel = "dirigera"
    icon = "bulb"
    order = 43
    forget = ["dirigera_host", "dirigera_token"]

    def status(self, adapter):
        if adapter.connected:
            return True
        return False if adapter.error else None

    def preset(self):
        return bool(config.DIRIGERA_HOST and config.DIRIGERA_TOKEN)

    def details(self, adapter):
        return {"error": adapter.error, "paired": bool(config.DIRIGERA_TOKEN), "address": config.DIRIGERA_HOST,
                "pairing": adapter._pairing is not None}

    def on_remove(self, hub, adapter):
        for device_id in [d.id for d in hub.devices.values() if d.source == "dirigera"]:
            hub.remove(device_id)
        adapter.connected = False

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.post("/api/dirigera/pair")
        async def pair(body: PairBody) -> dict:
            try:
                paired = await adapter.pair(body.host)
            except (ValueError, RuntimeError) as err:
                raise HTTPException(400, str(err))
            return {**ctx.describe("dirigera"), "paired_now": paired}

        return router


PLUGIN = DirigeraPlugin()
