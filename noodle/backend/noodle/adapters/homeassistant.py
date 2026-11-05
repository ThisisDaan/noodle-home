"""Home Assistant: bring in the devices it controls (lights, switches, fans, covers, locks, sensors) over its
local WebSocket API. Changes are pushed by Home Assistant, nothing is polled. The token is a "long-lived access
token" made on your Home Assistant profile page.

Use it for what Noodle has no integration for. A device that is also paired directly with Noodle (Hue, Zigbee)
would show up twice, so leave those out of Home Assistant's list or do not add them here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import websockets

from .. import config
from ..hub import Device, Entity, Hub

log = logging.getLogger(__name__)

DOMAINS = {"light", "switch", "fan", "cover", "lock", "sensor", "binary_sensor", "input_boolean", "event"}
SKIP_ATTR_DOMAINS = {"sensor": {"timestamp"}}


def entity_from_state(state: dict) -> Entity | None:
    """A hub entity for one Home Assistant state, or None for the kinds we do not use."""
    entity_id = state["entity_id"]
    domain = entity_id.split(".", 1)[0]
    if domain not in DOMAINS:
        return None
    attrs = state.get("attributes") or {}
    key = entity_id.replace(".", "__")
    name = str(attrs.get("friendly_name") or entity_id)
    raw = state.get("state")
    gone = raw in ("unknown", "unavailable", None)  # Home Assistant does not know: that is not "off"
    if domain == "event":  # a button or remote: each press is an event with a type ("single", "on", ...)
        types = attrs.get("event_types")
        return Entity(key, "button", name, actions=[str(t) for t in types]) if types else None
    if domain in ("switch", "input_boolean"):
        return Entity(key, "switch", name, state=None if gone else raw == "on")
    if domain == "fan":
        return Entity(key, "fan", name, state=None if gone else raw == "on")
    if domain == "light":
        modes = attrs.get("supported_color_modes") or []
        can = [c for c, m in (("color_temp", {"color_temp"}), ("color", {"hs", "rgb", "xy", "rgbw", "rgbww"})) if m & set(modes)]
        out = {"can": can}
        if "color_temp" in can:
            out["color_temp"] = attrs.get("color_temp_kelvin") or 3000
            out["color_temp_range"] = [attrs.get("min_color_temp_kelvin") or 2000, attrs.get("max_color_temp_kelvin") or 6500]
        if "color" in can and attrs.get("hs_color"):
            out["color"] = {"h": attrs["hs_color"][0], "s": attrs["hs_color"][1]}
        bri = attrs.get("brightness")
        dimmable = bool(set(modes) - {"onoff"})  # a light that is off reports no brightness, but it can still dim
        level = round(bri / 255 * 100) if bri is not None else (0 if dimmable else None)
        return Entity(key, "light", name, state=None if gone else raw == "on", brightness=level, attrs=out)
    if domain == "cover":
        pos = attrs.get("current_position")
        return Entity(key, "cover", name, state=None if gone else "open" if raw in ("open", "opening") else "closed",
                      attrs={"position": pos} if pos is not None else {})
    if domain == "lock":
        return Entity(key, "lock", name, state=None if gone else "locked" if raw == "locked" else "unlocked")
    if domain == "binary_sensor":
        return Entity(key, "binary_sensor", name, state=None if gone else raw == "on", device_class=attrs.get("device_class"))
    if gone:
        value = None
    else:
        try:
            value = round(float(raw), 2)
        except ValueError:
            value = str(raw)
    return Entity(key, "sensor", name, state=value, unit=attrs.get("unit_of_measurement"), device_class=attrs.get("device_class"))


def service_for(domain: str, entity_id: str, on: bool | None, brightness: int | None, toggle: bool, extra: dict) -> tuple[str, str, dict]:
    """(domain, service, data) for a command."""
    data: dict = {}
    if domain == "cover":
        if "position" in extra:
            return "cover", "set_cover_position", {"position": round(extra["position"])}
        return "cover", {"open": "open_cover", "close": "close_cover", "stop": "stop_cover"}[extra["action"]], data
    if domain == "lock":
        return "lock", "lock" if extra.get("action") == "lock" else "unlock", data
    if toggle:
        return domain, "toggle", data
    if domain == "light" and (brightness is not None or "color_temp" in extra or "color" in extra):
        if brightness is not None:
            data["brightness_pct"] = brightness
        if "color_temp" in extra:
            data["color_temp_kelvin"] = extra["color_temp"]
        if "color" in extra:
            data["hs_color"] = [extra["color"]["h"], extra["color"]["s"]]
        return "light", "turn_on", data
    return domain, "turn_on" if on else "turn_off", data


class HomeAssistantAdapter:
    source = "homeassistant"
    extra_commands = frozenset({"color_temp", "color", "position", "action"})

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.ws = None
        self.connected = False
        self.error: str | None = None
        self.entity_device: dict[str, str] = {}  # entity_id -> hub device id
        self.devices_reg: dict[str, dict] = {}  # Home Assistant's device registry
        self.registry: dict[str, dict] = {}  # and its entity registry
        self.last_event: dict[str, str] = {}  # event entity -> the time of its last event
        self.names: dict[str, str] = {}
        self.live = False  # false while the first list of states is read: events in it are old, not presses
        self._next = 1
        self._waiting: dict[int, asyncio.Future] = {}

    async def run(self) -> None:
        while True:
            if config.HA_URL and config.HA_TOKEN:
                try:
                    await self._session()
                except Exception as err:
                    self.error = str(err) or err.__class__.__name__
                    log.warning("Home Assistant connection lost (%s), retrying in 10s", self.error)
                finally:
                    self.connected, self.ws, self.live = False, None, False
            await asyncio.sleep(10)

    async def _call(self, message: dict) -> dict:
        message_id = self._next
        self._next += 1
        future = asyncio.get_running_loop().create_future()
        self._waiting[message_id] = future
        await self.ws.send(json.dumps({"id": message_id, **message}))
        return await asyncio.wait_for(future, 20)

    async def _session(self) -> None:
        url = config.HA_URL.strip().rstrip("/")
        url = url.replace("https://", "wss://", 1) if url.startswith("https://") else url.replace("http://", "ws://", 1)
        if not url.startswith(("ws://", "wss://")):
            url = "ws://" + url
        async with websockets.connect(f"{url}/api/websocket", max_size=32 * 1024 * 1024) as ws:
            self.ws = ws
            hello = json.loads(await ws.recv())
            if hello.get("type") != "auth_required":
                raise RuntimeError("That is not Home Assistant")
            await ws.send(json.dumps({"type": "auth", "access_token": config.HA_TOKEN}))
            if json.loads(await ws.recv()).get("type") != "auth_ok":
                raise RuntimeError("Home Assistant did not accept the token")
            reader = asyncio.create_task(self._read(ws))
            try:
                await self._subscribe()
                self.connected, self.error = True, None
                await reader
            finally:
                reader.cancel()
                for future in self._waiting.values():
                    future.cancel()
                self._waiting.clear()

    async def _subscribe(self) -> None:
        await self._call({"type": "subscribe_events", "event_type": "state_changed"})
        self.devices_reg = {d["id"]: d for d in (await self._call({"type": "config/device_registry/list"})).get("result") or []}
        self.registry = {e["entity_id"]: e for e in (await self._call({"type": "config/entity_registry/list"})).get("result") or []}
        for state in (await self._call({"type": "get_states"})).get("result") or []:
            self._apply(state)
        self.live = True

    async def _read(self, ws) -> None:
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "result" and (future := self._waiting.pop(msg["id"], None)):
                if not future.done():
                    future.set_result(msg)
            elif msg.get("type") == "event":
                new = (msg.get("event") or {}).get("data", {}).get("new_state")
                if new:
                    self._apply(new)

    def _device_for(self, entity_id: str, entity: Entity) -> Device | None:
        """The hub device an entity belongs to: its Home Assistant device, or one of its own."""
        device_id = self.entity_device.get(entity_id)
        if device_id is None:
            dev = self.devices_reg.get((self.registry.get(entity_id) or {}).get("device_id"))
            if dev:
                device_id = f"homeassistant:{dev['id']}"
                name, model, maker = dev.get("name_by_user") or dev.get("name") or entity_id, dev.get("model"), dev.get("manufacturer")
            elif entity.kind == "button":
                return None  # an event with no device (the backup, ...) is not a button
            else:
                device_id = f"homeassistant:{entity_id.replace('.', '__')}"
                name, model, maker = entity.name, None, None
            self.entity_device[entity_id] = device_id
            if device_id not in self.hub.devices:
                self.hub.upsert(Device(id=device_id, source=self.source, name=str(name), model=model,
                                       manufacturer=maker or "Home Assistant"))
        return self.hub.devices.get(device_id)

    def _apply(self, state: dict) -> None:
        entity = entity_from_state(state)
        if entity is None:
            return
        entity_id = state["entity_id"]
        reg = self.registry.get(entity_id) or {}
        if reg.get("disabled_by") or reg.get("hidden_by"):
            return
        attrs = state.get("attributes") or {}
        battery = entity.kind == "sensor" and attrs.get("device_class") == "battery"
        if reg.get("entity_category") and not battery:
            return  # diagnostics and settings (voltage, the chip's temperature, identify, ...) are not the device
        device = self._device_for(entity_id, entity)
        if device is None:
            return
        raw = state.get("state")
        if battery:  # shown as the device's battery, not as a sensor of its own
            if isinstance(entity.state, (int, float)):
                device.battery = int(entity.state)
        elif entity.kind == "button":
            old = self.last_event.get(entity_id)
            self.last_event[entity_id] = raw
            if entity.key not in device.entities:
                device.entities[entity.key] = entity
                self.hub.changed(device)
            if self.live and old is not None and raw != old and raw not in ("unknown", "unavailable", None):
                self.hub.event(device, entity.key, str(attrs.get("event_type") or "press"))
            return
        else:
            old = device.entities.get(entity.key)
            if old is None:
                device.entities[entity.key] = entity
            else:
                old.state, old.brightness, old.attrs, old.unit = entity.state, entity.brightness, entity.attrs, entity.unit
        real = [e for e in device.entities.values() if e.kind != "button"]
        device.available = not real or any(e.state is not None for e in real)  # all unknown: the device is not reporting
        if device.available:
            device.last_seen = time.time()
        self.hub.changed(device)

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool,
                      **extra) -> None:
        if not self.connected or self.ws is None:
            raise RuntimeError("Home Assistant is not connected")
        entity_id = entity.key.replace("__", ".", 1)
        domain, service, data = service_for(entity_id.split(".", 1)[0], entity_id, on, brightness, toggle, extra)
        await self._call({"type": "call_service", "domain": domain, "service": service, "service_data": data,
                          "target": {"entity_id": entity_id}})
