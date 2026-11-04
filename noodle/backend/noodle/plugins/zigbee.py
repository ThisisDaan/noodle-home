"""Zigbee devices through Zigbee2MQTT."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as BodyField

from ..adapters.zigbee import ZigbeeAdapter
from .base import Field, Plugin


class PermitJoinBody(BaseModel):
    seconds: int = BodyField(default=60, ge=0, le=254)


class ZigbeePlugin(Plugin):
    id = "zigbee"
    source = "zigbee"
    adapter_class = ZigbeeAdapter
    name = "Zigbee (Zigbee2MQTT)"
    help = ("Noodle talks to Zigbee2MQTT through an MQTT broker (for example Mosquitto). Point it at the broker "
            "Zigbee2MQTT uses. The web address is only for the links to Zigbee2MQTT's own pages.")
    fields = [Field("mqtt_host", "MQTT broker address", "127.0.0.1"), Field("mqtt_port", "MQTT port", "1883"),
              Field("z2m_base_topic", "Zigbee2MQTT base topic", "zigbee2mqtt"),
              Field("z2m_url", "Zigbee2MQTT web address (optional)", "http://192.168.1.10:8081")]
    gated = True
    icon = "wifi"
    order = 10

    def status(self, adapter):
        return adapter.client is not None and adapter.bridge.get("online", False)

    def preset(self):
        return True

    def system_info(self, adapter):
        return {"connected": adapter.client is not None, **adapter.bridge}

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.post("/api/zigbee/permit_join")
        async def permit_join(body: PermitJoinBody) -> dict:
            try:
                await adapter.permit_join(body.seconds)
            except RuntimeError as err:
                raise HTTPException(400, str(err))
            return {"ok": True}

        return router


PLUGIN = ZigbeePlugin()
