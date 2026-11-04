"""Zigbee via Zigbee2MQTT over MQTT.

Reads <base>/bridge/devices for the device list and <base>/<friendly_name> for
state; sends <base>/<friendly_name>/set to control lights and switches.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import time

import aiomqtt

from .. import config
from ..hub import Device, Entity, Hub

log = logging.getLogger(__name__)

# exposed property -> (kind, device_class, unit)
SENSORS = {
    "illuminance": ("sensor", "illuminance", "lx"),
    "temperature": ("sensor", "temperature", "°C"),
    "device_temperature": ("sensor", "device_temperature", "°C"),  # the chip, not the room
    "humidity": ("sensor", "humidity", "%"),
    "power": ("sensor", "power", "W"),
    "energy": ("sensor", "energy", "kWh"),
    "voltage": ("sensor", "voltage", "V"),
    "current": ("sensor", "current", "A"),
}
# battery-device voltage is in mV and not interesting on a dashboard
SKIP = {"linkquality", "power_outage_count", "trigger_count", "battery", "countdown",
        "power_outage_memory", "indicator_mode", "child_lock", "power_on_behavior", "effect",
        "color_temp_startup"}


class ZigbeeAdapter:
    source = "zigbee"

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.base = config.Z2M_BASE_TOPIC
        self.client: aiomqtt.Client | None = None
        self.friendly: dict[str, str] = {}  # device id -> friendly_name
        self.by_friendly: dict[str, str] = {}  # friendly_name -> device id
        self.bridge: dict = {"online": False, "permit_join": False, "version": None}
        # Called with a name for messages on homepi/hook/<name> (e.g. Hue presses forwarded by Home Assistant).
        self.on_hook = None

    @staticmethod
    def _id(ieee: str) -> str:
        return f"zigbee:{ieee}"

    async def run(self) -> None:
        while True:
            try:
                # A per-host client id, so a second instance (e.g. local development) does not kick this one off.
                identifier = f"homepi-{socket.gethostname()}"
                async with aiomqtt.Client(config.MQTT_HOST, config.MQTT_PORT, identifier=identifier) as client:
                    self.client = client
                    await client.subscribe(f"{self.base}/#")
                    await client.subscribe("homepi/hook/#")
                    log.info("connected to MQTT %s:%s", config.MQTT_HOST, config.MQTT_PORT)
                    async for message in client.messages:
                        try:
                            self._handle(str(message.topic), message.payload)
                        except Exception:
                            log.exception("bad message on %s", message.topic)
            except aiomqtt.MqttError as err:
                log.warning("MQTT connection lost (%s), retrying in 5s", err)
            finally:
                self.client = None
            await asyncio.sleep(5)

    def _handle(self, topic: str, payload: bytes) -> None:
        if topic.startswith("homepi/hook/"):
            if self.on_hook:
                self.on_hook(topic.split("/", 2)[2])
            return
        sub = topic[len(self.base) + 1:]
        if sub == "bridge/devices":
            self._load_devices(json.loads(payload))
        elif sub == "bridge/info":
            info = json.loads(payload)
            self.bridge.update(version=info.get("version"), permit_join=info.get("permit_join", False))
        elif sub == "bridge/state":
            text = payload.decode()
            self.bridge["online"] = (json.loads(text).get("state") if text.startswith("{") else text) == "online"
        elif sub.startswith("bridge/"):
            return
        elif sub.endswith("/availability"):
            device_id = self.by_friendly.get(sub.rsplit("/", 1)[0])
            if device_id in self.hub.devices:
                text = payload.decode()
                state = json.loads(text).get("state") if text.startswith("{") else text
                device = self.hub.devices[device_id]
                device.available = state == "online"
                self.hub.changed(device)
        elif "/" not in sub and payload:
            device_id = self.by_friendly.get(sub)
            if device_id in self.hub.devices:
                self._apply_state(self.hub.devices[device_id], json.loads(payload))

    def _load_devices(self, devices: list[dict]) -> None:
        seen = set()
        for d in devices:
            if d.get("type") == "Coordinator" or not d.get("definition"):
                continue
            device_id = self._id(d["ieee_address"])
            seen.add(device_id)
            friendly = d["friendly_name"]
            self.friendly[device_id] = friendly
            self.by_friendly[friendly] = device_id
            existing = self.hub.devices.get(device_id)
            device = Device(
                id=device_id,
                source=self.source,
                name=friendly,
                model=d["definition"].get("model"),
                manufacturer=d["definition"].get("vendor"),
                entities=self._entities(d["definition"].get("exposes", [])),
            )
            if existing:  # keep known state across device list refreshes
                device.battery, device.available = existing.battery, existing.available
                for key, entity in device.entities.items():
                    if key in existing.entities:
                        old = existing.entities[key]
                        entity.state, entity.brightness = old.state, old.brightness
            self.hub.upsert(device)
        for device_id in [i for i, dev in self.hub.devices.items() if dev.source == self.source and i not in seen]:
            self.hub.remove(device_id)
        # Device states are not retained, so ask lights and switches for theirs.
        asyncio.get_running_loop().create_task(self._request_states(seen))

    async def _request_states(self, device_ids: set[str]) -> None:
        for device_id in device_ids:
            device = self.hub.devices.get(device_id)
            if self.client and device and any(e.kind in ("light", "switch") for e in device.entities.values()):
                await self.client.publish(f"{self.base}/{self.friendly[device_id]}/get", json.dumps({"state": ""}))

    def _entities(self, exposes: list[dict]) -> dict[str, Entity]:
        entities: dict[str, Entity] = {}
        for e in exposes:
            if e.get("type") in ("light", "switch"):
                props = {f.get("property") for f in e.get("features", [])}
                key = "light" if e["type"] == "light" else "switch"
                entities[key] = Entity(key=key, kind=e["type"], name=e["type"].capitalize(),
                                       brightness=0 if "brightness" in props else None)
                continue
            prop = e.get("property")
            if not prop or prop in SKIP:
                continue
            if prop == "occupancy":
                entities[prop] = Entity(key=prop, kind="binary_sensor", name="Motion", device_class="occupancy")
            elif prop == "contact":
                entities[prop] = Entity(key=prop, kind="binary_sensor", name="Open", device_class="contact")
            elif prop == "action":
                entities[prop] = Entity(key=prop, kind="button", name="Button", actions=e.get("values") or None)
            elif prop in SENSORS:
                kind, device_class, unit = SENSORS[prop]
                if prop == "voltage" and e.get("unit") == "mV":
                    continue
                entities[prop] = Entity(key=prop, kind=kind, name=prop.replace("_", " ").capitalize(),
                                        unit=e.get("unit") or unit, device_class=device_class)
        return entities

    def _apply_state(self, device: Device, state: dict) -> None:
        if "battery" in state and state["battery"] is not None:
            device.battery = int(state["battery"])
        for key, entity in device.entities.items():
            if entity.kind in ("light", "switch") and "state" in state:
                entity.state = state["state"] == "ON"
                if entity.brightness is not None and state.get("brightness") is not None:
                    entity.brightness = round(state["brightness"] / 254 * 100)
            elif key == "contact" and key in state:
                entity.state = not state[key]  # contact=true means closed
            elif key == "action":
                if state.get("action"):
                    entity.state = state["action"]
                    self.hub.event(device, key, state["action"])
            elif key in state:
                entity.state = state[key]
        device.last_seen = time.time()
        self.hub.changed(device)

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool) -> None:
        if not self.client:
            raise RuntimeError("MQTT not connected")
        payload: dict = {}
        if toggle:
            payload["state"] = "TOGGLE"
        elif on is not None:
            payload["state"] = "ON" if on else "OFF"
        if brightness is not None and entity.kind == "light":
            payload["brightness"] = max(1, min(254, round(brightness / 100 * 254)))
            payload.setdefault("state", "ON")
        await self.client.publish(f"{self.base}/{self.friendly[device.id]}/set", json.dumps(payload))

    async def permit_join(self, seconds: int) -> None:
        if not self.client:
            raise RuntimeError("MQTT not connected")
        await self.client.publish(f"{self.base}/bridge/request/permit_join", json.dumps({"time": seconds}))
