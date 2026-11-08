"""IKEA DIRIGERA hub (see adapter.py)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import config
from .adapter import DirigeraAdapter
from ..base import Field, Plugin, PressButton


class PairBody(BaseModel):
    host: str


class DirigeraPlugin(Plugin):
    id = "dirigera"
    source = "dirigera"
    adapter_class = DirigeraAdapter
    name = "IKEA DIRIGERA"
    help = ("Lights, outlets, blinds and sensors on your IKEA DIRIGERA hub, controlled over your network: no cloud. "
            "Press Search to find the hub, then press the action button on it when asked. Or enter its IP address by hand.")
    fields = [Field("dirigera_host", "Hub address", hidden=True), Field("dirigera_token", "Token", secret=True, hidden=True)]
    gated = True
    panel = "dirigera"
    icon = "bulb"
    order = 43
    forget = ["dirigera_host", "dirigera_token"]
    searchable = True
    search_finds = "hub"
    noun = "IKEA hubs"
    press_hint = "Press the action button on the bottom of the DIRIGERA hub."
    restart_after_add = True

    def preset(self):
        return bool(config.DIRIGERA_HOST and config.DIRIGERA_TOKEN)

    def details(self, adapter):
        return {"error": adapter.error, "paired": bool(config.DIRIGERA_TOKEN), "address": config.DIRIGERA_HOST,
                "pairing": adapter._pairing is not None}

    async def add_found(self, adapter, key):
        try:
            paired = await adapter.pair(key)
        except RuntimeError as err:
            raise ValueError(str(err))
        if not paired:
            raise PressButton("Press the action button on the hub")

    def on_remove(self, hub, adapter):
        super().on_remove(hub, adapter)
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
