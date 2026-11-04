"""Philips Hue bridge."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as BodyField

from .. import config
from ..adapters import hue as hue_adapter
from ..adapters.hue import HueAdapter
from .base import Field, Plugin


class HuePairBody(BaseModel):
    host: str = BodyField(min_length=3, max_length=100)


class HuePlugin(Plugin):
    id = "hue"
    source = "hue"
    adapter_class = HueAdapter
    name = "Philips Hue"
    help = ("Connects to your Hue bridge so its lights, switches and sensors show up here. Find the bridge, "
            "press the round button on top of it, then pair.")
    fields = [Field("hue_host", "Hue bridge address", "192.168.1.20"),
              Field("hue_key", "Application key", "filled in by pairing", secret=True)]
    icon = "bulb"
    panel = "hue"
    custom_form = True
    forget = ["hue_host", "hue_key"]
    order = 30

    def status(self, adapter):
        return adapter.connected if config.HUE_HOST and config.HUE_KEY else None

    def preset(self):
        return bool(config.HUE_HOST)

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.post("/api/hue/discover")
        async def hue_discover() -> dict:
            try:
                return {"bridges": await hue_adapter.discover()}
            except Exception as err:
                raise HTTPException(400, f"Could not look for bridges: {err}")

        @router.post("/api/hue/pair")
        async def hue_pair(body: HuePairBody) -> dict:
            host = body.host.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
            try:
                key = await hue_adapter.pair(host)
            except hue_adapter.ButtonNotPressed as err:
                raise HTTPException(409, str(err))  # not an error: the page keeps asking until the button is pressed
            except ValueError as err:
                raise HTTPException(400, str(err))
            except Exception as err:
                raise HTTPException(400, f"Could not reach the bridge at {host}: {err}")
            config.save({"hue_host": host, "hue_key": key})
            await ctx.restart_adapter("hue")
            await asyncio.sleep(2.5)
            return ctx.describe("hue")

        return router


PLUGIN = HuePlugin()
