"""Combined devices: a few devices made into one (a sensor and a plug into a heater). See adapter.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..base import Plugin
from .adapter import CombinedAdapter
from .templates import TEMPLATES


class CombinedBody(BaseModel):
    template: str
    name: str = Field(max_length=60)
    values: dict = {}


class CombinedPlugin(Plugin):
    id = "combined"
    name = "Combined devices"
    source = "combined"
    adapter_class = CombinedAdapter
    visible = False
    order = 220

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.get("/api/combined/templates")
        def templates() -> list[dict]:
            return [{"id": t.id, "name": t.name, "help": t.help,
                     "inputs": [{"key": i.key, "kind": i.kind, "label": i.label, "default": i.default,
                                 "device_class": i.device_class} for i in t.inputs]}
                    for t in TEMPLATES.values()]

        @router.get("/api/combined")
        def items() -> list[dict]:
            return list(adapter.items.values())

        @router.post("/api/combined")
        def create(body: CombinedBody) -> dict:
            try:
                return adapter.save(body.template, body.name, body.values)
            except ValueError as err:
                raise HTTPException(400, str(err))

        @router.put("/api/combined/{cid}")
        def update(cid: str, body: CombinedBody) -> dict:
            if cid not in adapter.items:
                raise HTTPException(404, "Unknown combined device")
            try:
                return adapter.save(body.template, body.name, body.values, cid)
            except ValueError as err:
                raise HTTPException(400, str(err))

        @router.delete("/api/combined/{cid}")
        def delete(cid: str) -> dict:
            adapter.delete(cid)
            return {"ok": True}

        return router


PLUGIN = CombinedPlugin()
