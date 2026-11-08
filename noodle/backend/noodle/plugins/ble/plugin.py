"""Bluetooth temperature and humidity sensors (Xiaomi, Govee)."""

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field as BodyField

from ... import config
from .adapter import BleAdapter
from ..base import Plugin


class BleSensorBody(BaseModel):
    address: str = BodyField(min_length=11, max_length=40)
    name: str = BodyField(default="", max_length=60)


class BlePlugin(Plugin):
    id = "ble"
    source = "ble"
    adapter_class = BleAdapter
    name = "Bluetooth"
    help = ("Temperature and humidity sensors that broadcast over Bluetooth (Xiaomi, Govee). This machine needs "
            "Bluetooth. Switch a sensor on near it, and it shows up in the list to add.")
    gated = True
    searchable = True
    noun = "Bluetooth sensors"
    search_hint = "Put a battery in the sensor, or hold it near this machine."
    restart_after_add = True
    support = "supported"
    icon = "bluetooth"
    panel = "ble"
    forget = ["ble_sensors"]
    order = 40

    def status(self, adapter):
        return adapter.scanning if config.BLE_SENSORS or adapter.scanning else None

    def preset(self):
        return bool(config.BLE_SENSORS)

    def details(self, adapter):
        return {"sensors": adapter.sensor_list(), "error": adapter.error}

    async def add_found(self, adapter, key):
        row = adapter.nearby.get(key.upper())
        if row is None:
            raise KeyError("That sensor is no longer in range; search again")
        config.save({"ble_sensors": adapter.pairs_after(config.BLE_SENSORS, row["address"], row["name"] or row["kind"] or row["address"])})

    def on_remove(self, hub, adapter):
        super().on_remove(hub, adapter)

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        @router.get("/api/ble/nearby")
        def ble_nearby() -> dict:
            return {"scanning": adapter.scanning, "error": adapter.error, "devices": adapter.list_nearby()}

        @router.post("/api/ble/sensors")
        async def ble_add_sensor(body: BleSensorBody) -> dict:
            config.save({"ble_sensors": adapter.pairs_after(config.BLE_SENSORS, body.address, body.name or body.address)})
            await ctx.restart_adapter("ble")
            await asyncio.sleep(0.5)
            return ctx.describe("ble")

        @router.delete("/api/ble/sensors/{address}")
        async def ble_remove_sensor(address: str) -> dict:
            config.save({"ble_sensors": adapter.pairs_after(config.BLE_SENSORS, address, None)})
            await ctx.restart_adapter("ble")
            await asyncio.sleep(0.5)
            return ctx.describe("ble")

        return router


PLUGIN = BlePlugin()
