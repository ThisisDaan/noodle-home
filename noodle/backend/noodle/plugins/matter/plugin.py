"""Matter devices through python-matter-server, and Thread through an OpenThread border router."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as BodyField

from . import otbr
from .adapter import MatterAdapter
from ..base import Field, Plugin


class CommissionBody(BaseModel):
    code: str = BodyField(min_length=11, max_length=64)


class MatterPlugin(Plugin):
    id = "matter"
    source = "matter"
    adapter_class = MatterAdapter
    name = "Matter and Thread"
    help = ("A Matter server (python-matter-server) runs Matter devices; an OpenThread border router (OTBR) is "
            "needed for Thread devices. Both are optional.")
    fields = [Field("matter_url", "Matter server address", "ws://127.0.0.1:5580/ws"),
              Field("otbr_url", "Thread border router address", "http://127.0.0.1:8082")]
    gated = True
    panel = "matter"
    support = "supported"
    manual_add = True
    add_text = "Pair with its setup code or QR text"
    icon = "circle"
    order = 20

    def status(self, adapter):
        return adapter.ws is not None

    def preset(self):
        return True

    async def system_info(self, adapter):
        info = adapter.server_info
        return {"connected": adapter.ws is not None, "thread": await otbr.status(),
                **{k: info.get(k) for k in ("sdk_version", "fabric_id", "bluetooth_enabled", "thread_credentials_set")}}

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.post("/api/matter/commission")
        async def matter_commission(body: CommissionBody) -> dict:
            code = body.code.strip().replace("-", "").replace(" ", "")
            try:
                dataset = await otbr.active_dataset_hex()
                node = await adapter.commission(code, dataset)
            except Exception as err:
                raise HTTPException(400, f"Pairing failed: {err}")
            return {"ok": True, "device_id": f"matter:{node['node_id']}"}

        return router


PLUGIN = MatterPlugin()
