"""Zigbee devices through Zigbee2MQTT."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as BodyField

from . import broker
from ... import config
from .adapter import ZigbeeAdapter
from ..base import Field, Plugin


class BrokerBody(BaseModel):
    host: str = BodyField(min_length=1, max_length=253)
    port: int = BodyField(default=broker.PORT, ge=1, le=65535)


class PermitJoinBody(BaseModel):
    seconds: int = BodyField(default=60, ge=0, le=254)


class ZigbeePlugin(Plugin):
    id = "zigbee"
    source = "zigbee"
    adapter_class = ZigbeeAdapter
    name = "Zigbee2MQTT"
    help = ("Needs a Zigbee USB stick with Zigbee2MQTT and an MQTT broker (for example Mosquitto) already running, "
            "on this machine or another. Point Noodle at the broker Zigbee2MQTT uses. The web address is only for the links to Zigbee2MQTT's own pages.")
    fields = [Field("mqtt_host", "MQTT broker address", "127.0.0.1"), Field("mqtt_port", "MQTT port", "1883"),
              Field("z2m_base_topic", "Zigbee2MQTT base topic", "zigbee2mqtt"),
              Field("z2m_url", "Zigbee2MQTT web address (optional)", "http://192.168.1.10:8081")]
    gated = True
    panel = "zigbee"
    searchable = True
    auto_search = False  # pairing opens the Zigbee network for new devices, so it waits for the button
    noun = "Zigbee devices"
    search_hint = "Put your device in pairing mode now (often hold its button for 5 seconds)."
    support = "supported"
    icon = "wifi"
    order = 10

    def status(self, adapter):
        return adapter.client is not None and adapter.bridge.get("online", False)

    def preset(self):
        return True

    def system_info(self, adapter):
        return {"connected": adapter.client is not None, "error": adapter.error, **adapter.bridge}

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.post("/api/zigbee/permit_join")
        async def permit_join(body: PermitJoinBody) -> dict:
            try:
                await adapter.permit_join(body.seconds)
            except RuntimeError as err:
                raise HTTPException(400, str(err))
            return {"ok": True}

        def state() -> dict:
            """Where the setup screens stand: broker reached, Zigbee2MQTT running."""
            return {"host": config.MQTT_HOST, "port": config.MQTT_PORT, "connected": adapter.client is not None,
                    "online": bool(adapter.bridge.get("online")), "version": adapter.bridge.get("version"),
                    "error": adapter.error}

        @router.post("/api/zigbee/broker/search")
        async def broker_search() -> dict:
            """Look for MQTT brokers for a few seconds (pushed over /api/ws as the search "zigbee-broker")."""
            return ctx.discovery.start("zigbee-broker", broker.find, seconds=20)

        @router.delete("/api/zigbee/broker/search")
        async def broker_stop() -> dict:
            return ctx.discovery.stop("zigbee-broker")

        @router.post("/api/zigbee/broker/use")
        async def broker_use(body: BrokerBody) -> dict:
            """Check the broker, and if it answers use it and report whether Zigbee2MQTT is running behind it."""
            host = body.host.strip().removeprefix("mqtt://").split("/")[0]
            if ":" in host and host.count(":") == 1:  # "host:port" typed in the address box
                host, port = host.split(":")
                body.port = int(port) if port.isdigit() else body.port
            if not host or " " in host:
                raise HTTPException(400, "That does not look like an address. Use something like 192.168.1.20.")
            found = await broker.probe(host, body.port, timeout=3)
            if found != "ok":
                raise HTTPException(400, broker.why_not(found, host, body.port))
            config.save({"mqtt_host": host, "mqtt_port": str(body.port)})
            await ctx.restart_adapter("zigbee")
            await asyncio.sleep(2.5)  # the broker's retained messages say whether Zigbee2MQTT is running
            return state()

        @router.get("/api/zigbee/setup")
        async def setup_state() -> dict:
            return state()

        return router


PLUGIN = ZigbeePlugin()
