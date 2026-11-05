"""The shared part of the plugins for devices that are reached by address (see adapters/lan.py). It has no
PLUGIN of its own; the plugins in this package build on it."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import config
from .base import Plugin


class HostBody(BaseModel):
    host: str


class LanPlugin(Plugin):
    gated = True
    searchable = True
    panel = "lan"
    restart_after_add = False
    icon = "plug"
    config_attr = ""  # the config attribute with the saved devices, e.g. "SHELLY_DEVICES"
    add_hint = "Search finds them on your network, or add one by its IP address."

    def status(self, adapter):
        if any(adapter.heard.get(k) for k in adapter.known):
            return True
        return False if adapter.known else None

    def preset(self):
        return bool(getattr(config, self.config_attr))

    def details(self, adapter):
        return {"devices": adapter.device_list(), "add_hint": self.add_hint}

    async def search(self, adapter, seconds, found):
        await adapter.search(seconds, found)

    async def add_found(self, adapter, key):
        await adapter.add_found(key)

    def on_remove(self, hub, adapter):
        for device_id in [d.id for d in hub.devices.values() if d.source == self.source]:
            hub.remove(device_id)
        adapter.known.clear()
        adapter.nearby.clear()

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])
        pid = self.id

        @router.post(f"/api/{pid}/devices", name=f"{pid}_add")
        async def add(body: HostBody) -> dict:
            try:
                await adapter.add_host(body.host)
            except (ValueError, RuntimeError) as err:
                raise HTTPException(400, str(err))
            return ctx.describe(pid)

        @router.delete(f"/api/{pid}/devices/{{key}}", name=f"{pid}_forget")
        async def forget(key: str) -> dict:
            adapter.forget(key)
            return ctx.describe(pid)

        return router
