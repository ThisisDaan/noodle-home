"""Custom devices: devices you make yourself and flows write to. See adapter.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..base import Plugin
from .adapter import CustomAdapter


class FieldBody(BaseModel):
    key: str | None = None
    label: str = Field(max_length=40)
    type: str
    unit: str | None = Field(default=None, max_length=10)


class CustomBody(BaseModel):
    name: str = Field(max_length=60)
    fields: list[FieldBody] = []


class CustomPlugin(Plugin):
    id = "custom"
    name = "Custom devices"
    source = "custom"
    adapter_class = CustomAdapter
    visible = False
    order = 230

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.get("/api/custom")
        def listing() -> list[dict]:
            return adapter.listing()

        @router.post("/api/custom")
        def create(body: CustomBody) -> dict:
            try:
                return adapter.save(body.name, [f.model_dump() for f in body.fields])
            except ValueError as err:
                raise HTTPException(400, str(err))

        @router.put("/api/custom/{device_id}")
        def update(device_id: str, body: CustomBody) -> dict:
            try:
                return adapter.save(body.name, [f.model_dump() for f in body.fields], device_id)
            except KeyError:
                raise HTTPException(404, "Unknown custom device")
            except ValueError as err:
                raise HTTPException(400, str(err))

        @router.delete("/api/custom/{device_id}")
        def delete(device_id: str) -> dict:
            try:
                adapter.delete(device_id)
            except KeyError:
                raise HTTPException(404, "Unknown custom device")
            except ValueError as err:
                raise HTTPException(400, str(err))
            return {"ok": True}

        return router


PLUGIN = CustomPlugin()
