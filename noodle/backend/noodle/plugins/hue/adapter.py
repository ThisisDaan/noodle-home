"""Philips Hue.

Two ways in, both optional:
- A Hue bridge (set its address and pair it on the Integrations page): every light, switch, motion, temperature
  and light sensor on the bridge becomes a device here, live over the bridge's event stream (API v2).
- Older setup: Hue Tap and Hue Dimmer switches that stay paired with the bridge only; a Home Assistant
  automation that forwards each press sends each press as MQTT noodle/hook/<name> (or the older homepi/hook/<name>). Those names become buttons
  on devices described in config/hue-hooks.yaml (see examples/hue-hooks.yaml), so flows use them with "Button pressed" like any other button.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx

from ... import config
from ...hub import Device, Entity, Hub
from ...yamlfile import YamlFile

log = logging.getLogger(__name__)

def _parse_legacy(path, stamp) -> dict:
    try:
        doc = YamlFile(path).read()
    except ValueError as err:
        log.warning("%s (no forwarded Hue buttons until it is fixed)", err)
        return {}
    out = {}
    for device_id, spec in doc.items():
        if not isinstance(spec, dict):
            continue
        buttons = {str(hook): (str(v[0]), str(v[1])) for hook, v in (spec.get("buttons") or {}).items()
                   if isinstance(v, (list, tuple)) and len(v) == 2}
        out[str(device_id)] = (str(spec.get("name") or device_id), str(spec.get("model") or "Hue switch"), buttons)
    return out


_legacy_cache: tuple = (None, {})


def legacy_switches() -> dict:
    """device id -> (name, model, {forwarded name: (button key, button name)}) for the older setup (see the module
    docstring), read from config/hue-hooks.yaml. Without that file there are none."""
    global _legacy_cache
    path = config.CONFIG_DIR / "hue-hooks.yaml"
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return {}
    if _legacy_cache[0] != (path, stamp):
        _legacy_cache = ((path, stamp), _parse_legacy(path, stamp))
    return _legacy_cache[1]


def legacy_buttons() -> dict:
    """forwarded name -> (device id, button key)"""
    return {name: (device_id, key) for device_id, (_, _, buttons) in legacy_switches().items()
            for name, (key, _) in buttons.items()}


# What the bridge calls a button press -> what flows see.
PRESSES = {"short_release": "press", "long_press": "hold"}


class Bridge:
    """Hue bridge API v2 over https. The bridge has a self-signed certificate, so it is not verified."""

    def __init__(self, host: str, key: str) -> None:
        self.http = httpx.AsyncClient(base_url=f"https://{host}", headers={"hue-application-key": key},
                                      verify=False, timeout=10)

    async def close(self) -> None:
        await self.http.aclose()

    async def get(self, path: str) -> list[dict]:
        response = await self.http.get(path)
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            raise RuntimeError(body["errors"][0].get("description", "Hue error"))
        return body["data"]

    async def put(self, path: str, body: dict) -> None:
        response = await self.http.put(path, json=body)
        response.raise_for_status()

    async def events(self):
        async with self.http.stream("GET", "/eventstream/clip/v2", headers={"Accept": "text/event-stream"},
                                    timeout=httpx.Timeout(10, read=None)) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    yield json.loads(line[5:])


MDNS = "_hue._tcp.local."  # what a Hue bridge announces itself as


async def discover(seconds: float, found) -> None:
    """Bridges on this network, from their own mDNS announcement: nothing leaves the local network. Calls
    found(address) for each one, during `seconds`."""
    from ... import mdns

    async def on_service(service_type, name, info) -> None:
        for host in mdns.ipv4(info)[:1]:
            found(host)

    await mdns.browse([MDNS], seconds, on_service)


class ButtonNotPressed(ValueError):
    """The bridge is reachable but its link button has not been pressed (yet)."""


async def pair(host: str) -> str:
    """Ask the bridge for an application key. The round link button on the bridge must have been pressed
    in the last 30 seconds."""
    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        response = await client.post(f"https://{host}/api", json={"devicetype": "noodle#hub", "generateclientkey": True})
        response.raise_for_status()
        result = response.json()[0]
    if "error" in result:
        if result["error"].get("type") == 101:
            raise ButtonNotPressed("Press the round button on top of the Hue bridge.")
        raise ValueError(result["error"].get("description", "Pairing failed"))
    return result["success"]["username"]


class HueAdapter:
    source = "hue"

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.bridges: dict[str, Bridge] = {}  # address -> the connection that is open to it
        self.state: dict[str, dict] = {}  # address -> {"connected": bool, "error": str | None}
        self.rid: dict[str, tuple[str, str]] = {}  # bridge resource id -> (device id, entity key)
        self.owner: dict[str, str] = {}  # bridge resource id -> noodle device id
        self.light_ids: dict[str, tuple[str, str]] = {}  # noodle device id -> (bridge address, bridge light id)
        self.devices_of: dict[str, set[str]] = {}  # bridge address -> the noodle devices it has

    @property
    def connected(self) -> bool:
        return any(s["connected"] for s in self.state.values())

    @property
    def error(self) -> str | None:
        return next((s["error"] for s in self.state.values() if s["error"] and not s["connected"]), None)

    async def run(self) -> None:
        for device_id, (name, model, buttons) in legacy_switches().items():
            self.hub.upsert(Device(id=device_id, source=self.source, name=name, model=model,
                                   manufacturer="Philips Hue", entities={
                                       key: Entity(key, "button", label, actions=["press"]) for key, label in buttons.values()}))
        self.rid.clear()
        self.owner.clear()
        self.light_ids.clear()
        self.devices_of.clear()
        self.bridges.clear()
        self.state = {host: {"connected": False, "error": None} for host in config.hue_bridges()}
        await asyncio.gather(*(self._watch(host, key) for host, key in config.hue_bridges().items()))

    async def _watch(self, host: str, key: str) -> None:
        """Keep one bridge connected: read everything, follow its events, and try again when it drops."""
        while True:
            bridge = self.bridges[host] = Bridge(host, key)
            try:
                await self._load(bridge, host)
                self.state[host] = {"connected": True, "error": None}
                log.info("connected to Hue bridge %s", host)
                async for events in bridge.events():
                    for event in events:
                        for item in event.get("data", []):
                            self._apply(item)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self.state[host] = {"connected": False, "error": str(err) or type(err).__name__}
                log.warning("Hue bridge %s connection lost (%s), retrying in 10s", host, self.state[host]["error"])
            finally:
                self.state.setdefault(host, {"error": None})["connected"] = False
                await bridge.close()
                for device_id in self.devices_of.get(host, ()):
                    if device := self.hub.devices.get(device_id):
                        device.available = False
                        self.hub.changed(device)
            await asyncio.sleep(10)

    def forget_bridge(self, host: str) -> None:
        """A bridge was removed: its devices go away too."""
        for device_id in self.devices_of.pop(host, set()):
            self.hub.remove(device_id)
            self.light_ids.pop(device_id, None)
        self.state.pop(host, None)

    # --- bridge: read everything, then follow the event stream ----------------------------------

    async def _load(self, bridge: Bridge, host: str) -> None:
        resources = await bridge.get("/clip/v2/resource")
        by_type: dict[str, list[dict]] = {}
        for item in resources:
            by_type.setdefault(item["type"], []).append(item)
        for dev in by_type.get("device", []):
            product = dev.get("product_data", {})
            if product.get("product_name") == "Hue bridge" or product.get("model_id", "").startswith("BSB"):
                continue
            device_id = f"hue:{dev['id']}"
            self.devices_of.setdefault(host, set()).add(device_id)
            self.owner[dev["id"]] = device_id
            for svc in dev.get("services", []):
                self.owner[svc["rid"]] = device_id
            self.hub.upsert(Device(id=device_id, source=self.source, name=dev["metadata"]["name"],
                                   model=product.get("model_id"), manufacturer=product.get("manufacturer_name")))
        for kind, items in by_type.items():
            for item in items:
                device = self.hub.devices.get(self.owner.get(item.get("owner", {}).get("rid", ""), ""))
                if device is not None:
                    self._entity(device, kind, item, host)
        for device_id in self.devices_of.get(host, ()):
            if device := self.hub.devices.get(device_id):
                device.available = True
                self.hub.changed(device)

    def _entity(self, device: Device, kind: str, item: dict, host: str) -> None:
        """Create the entity a bridge resource stands for (if it stands for one) and fill in its state."""
        key = ""
        if kind == "light":
            key = "light" if "light" not in device.entities else f"light_{len(device.entities)}"
            device.entities[key] = Entity(key, "light", "Light", brightness=0 if "dimming" in item else None)
            self.light_ids[device.id] = (host, item["id"])
        elif kind == "button":
            index = item.get("metadata", {}).get("control_id", len(device.entities) + 1)
            key = f"button_{index}"
            device.entities[key] = Entity(key, "button", f"Button {index}", actions=list(PRESSES.values()))
        elif kind == "motion":
            key = "motion"
            device.entities[key] = Entity(key, "binary_sensor", "Motion", device_class="occupancy")
        elif kind == "temperature":
            key = "temperature"
            device.entities[key] = Entity(key, "sensor", "Temperature", unit="°C", device_class="temperature")
        elif kind == "light_level":
            key = "illuminance"
            device.entities[key] = Entity(key, "sensor", "Light level", unit="lx", device_class="illuminance")
        elif kind not in ("device_power", "zigbee_connectivity"):
            return
        self.rid[item["id"]] = (device.id, key)
        self._set(device, kind, key, item, initial=True)

    def _apply(self, item: dict) -> None:
        target = self.rid.get(item.get("id", ""))
        if target is None:
            return
        device = self.hub.devices.get(target[0])
        if device is None:
            return
        self._set(device, item.get("type", ""), target[1], item)
        self.hub.changed(device)

    def _set(self, device: Device, kind: str, key: str, item: dict, initial: bool = False) -> None:
        entity = device.entities.get(key)
        if kind == "light" and entity:
            if "on" in item:
                entity.state = bool(item["on"].get("on"))
            if entity.brightness is not None and "dimming" in item:
                entity.brightness = round(item["dimming"].get("brightness", 0))
        elif kind == "button" and entity:
            button = item.get("button") or {}
            action = PRESSES.get(button.get("button_report", {}).get("event") or button.get("last_event") or "")
            if action and not initial:
                entity.state = action
                self.hub.event(device, key, action)
        elif kind == "motion" and entity:
            motion = item.get("motion") or {}
            value = motion.get("motion_report", {}).get("motion", motion.get("motion"))
            if value is not None:
                entity.state = bool(value)
        elif kind == "temperature" and entity:
            temp = item.get("temperature") or {}
            value = temp.get("temperature_report", {}).get("temperature", temp.get("temperature"))
            if value is not None:
                entity.state = round(value, 1)
        elif kind == "light_level" and entity:
            level = item.get("light") or {}
            value = level.get("light_level_report", {}).get("light_level", level.get("light_level"))
            if value is not None:
                entity.state = round(10 ** ((value - 1) / 10000))
        elif kind == "device_power":
            level = (item.get("power_state") or {}).get("battery_level")
            if level is not None:
                device.battery = int(level)
        elif kind == "zigbee_connectivity" and "status" in item:
            device.available = item["status"] == "connected"
        device.last_seen = time.time()

    # --- the old relay: switches that are only paired with the bridge ----------------------------

    def press(self, name: str) -> bool:
        """Handle a forwarded press; False when the name is not a Hue button (e.g. a phone notification button)."""
        buttons = legacy_buttons()
        if name not in buttons:
            return False
        device_id, key = buttons[name]
        device = self.hub.devices.get(device_id)
        if device:
            device.entities[key].state = "press"
            self.hub.changed(device)
            self.hub.event(device, key, "press")
        return True

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None,
                      toggle: bool) -> None:
        found = self.light_ids.get(device.id)
        if not found:
            raise ValueError("Hue switches can only be pressed by hand")
        host, light = found
        bridge = self.bridges.get(host)
        if bridge is None or not self.state.get(host, {}).get("connected"):
            raise RuntimeError("Hue bridge not connected")
        body: dict = {}
        if toggle:
            body["on"] = {"on": not entity.state}
        elif on is not None:
            body["on"] = {"on": on}
        if brightness is not None and entity.brightness is not None:
            body["dimming"] = {"brightness": max(1.0, min(100.0, float(brightness)))}
            body.setdefault("on", {"on": True})
        await bridge.put(f"/clip/v2/resource/light/{light}", body)
