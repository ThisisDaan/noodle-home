"""Zigbee via Zigbee2MQTT over MQTT.

Reads <base>/bridge/devices for the device list and <base>/<friendly_name> for
state; sends <base>/<friendly_name>/set to control lights, switches, fans, covers, locks and thermostats.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import time

import aiomqtt

from .. import config
from .. import capabilities
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


def _kelvin(mired: float) -> int:
    return round(1_000_000 / mired) if mired else 0


class ZigbeeAdapter:
    source = "zigbee"
    extra_commands = frozenset({"color_temp", "color", "position", "action", "mode", "value"})

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.base = config.Z2M_BASE_TOPIC
        self.client: aiomqtt.Client | None = None
        self.friendly: dict[str, str] = {}  # device id -> friendly_name
        self.by_friendly: dict[str, str] = {}  # friendly_name -> device id
        self.bridge: dict = {"online": False, "permit_join": False, "version": None}
        # Called with a name for messages on noodle/hook/<name> (or the older homepi/hook/<name>) (e.g. Hue presses forwarded by Home Assistant).
        self.on_hook = None

    @staticmethod
    def _id(ieee: str) -> str:
        return f"zigbee:{ieee}"

    async def run(self) -> None:
        while True:
            try:
                # A per-host client id, so a second instance (e.g. local development) does not kick this one off.
                identifier = f"noodle-{socket.gethostname()}"
                async with aiomqtt.Client(config.MQTT_HOST, config.MQTT_PORT, identifier=identifier) as client:
                    self.client = client
                    await client.subscribe(f"{self.base}/#")
                    await client.subscribe("noodle/hook/#")
                    await client.subscribe("homepi/hook/#")  # the name older setups send to
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
        if topic.startswith(("noodle/hook/", "homepi/hook/")):
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
                        entity.attrs = {**old.attrs, **entity.attrs}
            self.hub.upsert(device)
        for device_id in [i for i, dev in self.hub.devices.items() if dev.source == self.source and i not in seen]:
            self.hub.remove(device_id)
        # Device states are not retained, so ask lights and switches for theirs.
        asyncio.get_running_loop().create_task(self._request_states(seen))

    async def _request_states(self, device_ids: set[str]) -> None:
        for device_id in device_ids:
            device = self.hub.devices.get(device_id)
            if self.client and device and any(e.kind in ("light", "switch", "fan", "cover", "lock", "climate") for e in device.entities.values()):
                await self.client.publish(f"{self.base}/{self.friendly[device_id]}/get", json.dumps({"state": ""}))

    def _entities(self, exposes: list[dict]) -> dict[str, Entity]:
        entities: dict[str, Entity] = {}
        for e in exposes:
            kind = e.get("type")
            if kind in ("light", "switch", "fan", "cover", "lock", "climate"):
                features = {f.get("name"): f for f in e.get("features", [])}
                entity = getattr(self, f"_{kind}")(e, features)
                if entity:
                    entities[entity.key] = entity
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
                sensor, device_class, unit = SENSORS[prop]
                if prop == "voltage" and e.get("unit") == "mV":
                    continue
                entities[prop] = Entity(key=prop, kind=sensor, name=prop.replace("_", " ").capitalize(),
                                        unit=e.get("unit") or unit, device_class=device_class)
        return entities

    # One method per controllable expose type: read what the device can do into an Entity.
    def _light(self, e: dict, f: dict) -> Entity:
        can, attrs = [], {}
        if "color_temp" in f:
            can.append("color_temp")
            low, high = f["color_temp"].get("value_min"), f["color_temp"].get("value_max")
            if low and high:  # Zigbee2MQTT counts in mireds, where a bigger number is warmer
                attrs["color_temp_range"] = [_kelvin(high), _kelvin(low)]
        if "color_xy" in f or "color_hs" in f:
            can.append("color")
        attrs["can"] = can
        return Entity(key="light", kind="light", name="Light", brightness=0 if "brightness" in f else None, attrs=attrs)

    def _switch(self, e: dict, f: dict) -> Entity:
        return Entity(key="switch", kind="switch", name="Switch")

    def _fan(self, e: dict, f: dict) -> Entity:
        modes = (f.get("mode") or {}).get("values") or []
        return Entity(key="fan", kind="fan", name="Fan", attrs={"modes": modes} if modes else {})

    def _cover(self, e: dict, f: dict) -> Entity:
        return Entity(key="cover", kind="cover", name="Cover", attrs={"position": None} if "position" in f else {})

    def _lock(self, e: dict, f: dict) -> Entity:
        return Entity(key="lock", kind="lock", name="Lock")

    def _climate(self, e: dict, f: dict) -> Entity | None:
        target = next((n for n in ("occupied_heating_setpoint", "current_heating_setpoint", "occupied_cooling_setpoint")
                       if n in f), None)
        if target is None:
            return None
        attrs = {"target_property": target, "min": f[target].get("value_min"), "max": f[target].get("value_max"),
                 "step": f[target].get("value_step")}
        if "system_mode" in f:
            attrs["modes"] = f["system_mode"].get("values") or []
        return Entity(key="climate", kind="climate", name="Thermostat", unit=f[target].get("unit") or "°C", attrs=attrs)

    def _apply_state(self, device: Device, state: dict) -> None:
        if "battery" in state and state["battery"] is not None:
            device.battery = int(state["battery"])
        for key, entity in device.entities.items():
            if entity.kind in ("light", "switch", "fan") and "state" in state:
                entity.state = state["state"] == "ON"
                if entity.kind == "light":
                    self._apply_light(entity, state)
                elif state.get("mode") is not None:
                    entity.attrs["mode"] = state["mode"]
            elif entity.kind == "cover":
                self._apply_cover(entity, state)
            elif entity.kind == "lock":
                lock = str(state.get("lock_state") or state.get("state") or "").lower()
                if lock in ("locked", "lock", "unlocked", "unlock"):
                    entity.state = "locked" if lock in ("locked", "lock") else "unlocked"
            elif entity.kind == "climate":
                self._apply_climate(entity, state)
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

    def _apply_light(self, entity: Entity, state: dict) -> None:
        if entity.brightness is not None and state.get("brightness") is not None:
            entity.brightness = round(state["brightness"] / 254 * 100)
        if state.get("color_temp"):
            entity.attrs["color_temp"] = _kelvin(state["color_temp"])
        color = state.get("color")
        if isinstance(color, dict):
            if "hue" in color and "saturation" in color:
                entity.attrs["color"] = {"h": color["hue"], "s": color["saturation"]}
            elif "x" in color and "y" in color:
                entity.attrs["color"] = capabilities.xy_to_hs(color["x"], color["y"])

    def _apply_cover(self, entity: Entity, state: dict) -> None:
        position = state.get("position")
        if position is not None:
            entity.attrs["position"] = position
            entity.state = "open" if position > 0 else "closed"
        elif state.get("state") in ("OPEN", "CLOSE"):
            entity.state = "open" if state["state"] == "OPEN" else "closed"

    def _apply_climate(self, entity: Entity, state: dict) -> None:
        target = entity.attrs.get("target_property")
        if target in state and state[target] is not None:
            entity.state = state[target]
        if state.get("local_temperature") is not None:
            entity.attrs["current"] = state["local_temperature"]
        if state.get("system_mode") is not None:
            entity.attrs["mode"] = state["system_mode"]
        if state.get("running_state") is not None:
            entity.attrs["running"] = state["running_state"]

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool,
                      **extra) -> None:
        if not self.client:
            raise RuntimeError("MQTT not connected")
        payload: dict = {}
        if entity.kind in ("light", "switch", "fan"):
            if toggle:
                payload["state"] = "TOGGLE"
            elif on is not None:
                payload["state"] = "ON" if on else "OFF"
        if brightness is not None and entity.kind == "light":
            payload["brightness"] = max(1, min(254, round(brightness / 100 * 254)))
            payload.setdefault("state", "ON")
        if "color_temp" in extra:
            payload["color_temp"] = round(1_000_000 / extra["color_temp"])
            payload.setdefault("state", "ON")
        if "color" in extra:
            payload["color"] = {"hue": extra["color"]["h"], "saturation": extra["color"]["s"]}
            payload.setdefault("state", "ON")
        if entity.kind == "cover":
            if "position" in extra:
                payload["position"] = round(extra["position"])
            elif "action" in extra:
                payload["state"] = extra["action"].upper()
        elif entity.kind == "lock" and "action" in extra:
            payload["state"] = extra["action"].upper()
        elif entity.kind == "fan" and "mode" in extra:
            payload["mode"] = extra["mode"]
        elif entity.kind == "climate":
            if "value" in extra:
                payload[entity.attrs["target_property"]] = extra["value"]
            if "mode" in extra:
                payload["system_mode"] = extra["mode"]
        if not payload:
            raise ValueError(f"nothing to send to {device.name}")
        await self.client.publish(f"{self.base}/{self.friendly[device.id]}/set", json.dumps(payload))

    async def permit_join(self, seconds: int) -> None:
        if not self.client:
            raise RuntimeError("MQTT not connected")
        await self.client.publish(f"{self.base}/bridge/request/permit_join", json.dumps({"time": seconds}))
