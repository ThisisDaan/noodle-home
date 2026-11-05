"""Devices that announce themselves over MQTT with Home Assistant's discovery format: Tasmota, ESPHome,
Shelly (in MQTT mode), and most DIY MQTT devices. No cloud; it uses the same broker as Zigbee2MQTT.

Devices appear by themselves when they publish their (retained) config message on <prefix>/<component>/.../config.
That is the broker's own list, not a scan of the network. Supported: switches, lights (on/off, brightness, and
the JSON schema), sensors and binary sensors. Zigbee2MQTT's own announcements are skipped (the Zigbee
integration already has those devices).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import time

import aiomqtt

from .. import config
from ..hub import Device, Entity, Hub

log = logging.getLogger(__name__)

ABBREVIATIONS = {
    "stat_t": "state_topic", "cmd_t": "command_topic", "val_tpl": "value_template", "pl_on": "payload_on",
    "pl_off": "payload_off", "stat_on": "state_on", "stat_off": "state_off", "avty_t": "availability_topic",
    "pl_avail": "payload_available", "pl_not_avail": "payload_not_available", "dev_cla": "device_class",
    "unit_of_meas": "unit_of_measurement", "uniq_id": "unique_id", "obj_id": "object_id", "sch": "schema",
    "bri_cmd_t": "brightness_command_topic", "bri_stat_t": "brightness_state_topic",
    "bri_val_tpl": "brightness_value_template", "bri_scl": "brightness_scale", "dev": "device",
    "ids": "identifiers", "mdl": "model", "mf": "manufacturer",
}
COMPONENTS = {"switch", "light", "sensor", "binary_sensor"}


def expand(cfg):
    """Spell out the short keys and fill in the `~` base topic."""
    if isinstance(cfg, dict):
        out = {ABBREVIATIONS.get(k, k): expand(v) for k, v in cfg.items()}
        base = out.get("~")
        if base is not None:
            for k, v in out.items():
                if k.endswith(("_topic", "_t")) and isinstance(v, str):
                    out[k] = v.replace("~", base, 1) if v.startswith("~") else (v[:-1] + base if v.endswith("~") else v)
        return out
    if isinstance(cfg, list):
        return [expand(v) for v in cfg]
    return cfg


def extract(template: str | None, raw: str):
    """The value in a message. Understands `{{ value_json.a.b }}` and `{{ value_json['a'] }}`; with no template
    the message itself."""
    if not template:
        return raw
    m = re.search(r"value_json((?:\.\w+|\[['\"][^'\"]+['\"]\]|\[\d+\])+)", template)
    if not m:
        return raw
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    for part in re.findall(r"\.(\w+)|\[['\"]([^'\"]+)['\"]\]|\[(\d+)\]", m.group(1)):
        name = part[0] or part[1]
        try:
            value = value[name] if name else value[int(part[2])]
        except (KeyError, IndexError, TypeError):
            return None
    return value


def device_key(cfg: dict, topic_parts: list[str]) -> str:
    dev = cfg.get("device") or {}
    ids = dev.get("identifiers")
    first = ids[0] if isinstance(ids, list) and ids else ids
    raw = str(first or cfg.get("unique_id") or "/".join(topic_parts[:-2]))
    return re.sub(r"[^a-z0-9_.-]+", "_", raw.lower()).strip("_")


class MqttAdapter:
    source = "mqtt"
    extra_commands: frozenset[str] = frozenset()

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.client: aiomqtt.Client | None = None
        self.specs: dict[tuple[str, str], dict] = {}  # (device id, entity key) -> its config
        self.topics: dict[str, list[tuple[str, str]]] = {}  # state/availability topic -> who listens
        self.seen = False

    @property
    def prefix(self) -> str:
        return (config.MQTT_DISCOVERY_PREFIX or "homeassistant").strip("/")

    async def run(self) -> None:
        while True:
            try:
                identifier = f"noodle-disc-{socket.gethostname()}"
                async with aiomqtt.Client(config.MQTT_HOST, config.MQTT_PORT, identifier=identifier) as client:
                    self.client = client
                    self.topics.clear()
                    await client.subscribe(f"{self.prefix}/+/+/config")
                    await client.subscribe(f"{self.prefix}/+/+/+/config")
                    for topic in list(self.topics):
                        await client.subscribe(topic)
                    async for message in client.messages:
                        try:
                            await self._handle(str(message.topic), message.payload)
                        except Exception:
                            log.exception("bad MQTT discovery message on %s", message.topic)
            except aiomqtt.MqttError as err:
                log.warning("MQTT discovery connection lost (%s), retrying in 5s", err)
            finally:
                self.client = None
            await asyncio.sleep(5)

    async def _handle(self, topic: str, payload: bytes) -> None:
        if topic.startswith(self.prefix + "/") and topic.endswith("/config"):
            await self._discover(topic, payload)
            return
        for device_id, key in self.topics.get(topic, []):
            self._state(device_id, key, topic, payload.decode("utf-8", "replace"))

    async def _discover(self, topic: str, payload: bytes) -> None:
        parts = topic.split("/")
        component = parts[1]
        if component not in COMPONENTS or not payload:
            return
        cfg = expand(json.loads(payload))
        dev = cfg.get("device") or {}
        ids = str(dev.get("identifiers", ""))
        if "zigbee2mqtt" in ids.lower() or "zigbee2mqtt" in str(cfg.get("state_topic", "")).lower().split("/")[0]:
            return  # the Zigbee integration has these
        did = f"mqtt:{device_key(cfg, parts)}"
        key = re.sub(r"[^a-z0-9_]+", "_", str(cfg.get("object_id") or parts[-2]).lower()).strip("_") or "entity"
        device = self.hub.devices.get(did)
        entity = self._entity(component, key, cfg)
        if device is None:
            device = Device(id=did, source=self.source, name=str(dev.get("name") or cfg.get("name") or did),
                            model=dev.get("model"), manufacturer=dev.get("manufacturer"), entities={key: entity},
                            available=cfg.get("availability_topic") is None)
            self.hub.upsert(device)
        elif key not in device.entities:
            device.entities[key] = entity
            self.hub.changed(device)
        self.specs[(did, key)] = {"component": component, **cfg}
        for t in {cfg.get("state_topic"), cfg.get("brightness_state_topic"), cfg.get("availability_topic")} - {None}:
            listeners = self.topics.setdefault(t, [])
            if (did, key) not in listeners:
                listeners.append((did, key))
            if self.client:
                await self.client.subscribe(t)

    @staticmethod
    def _entity(component: str, key: str, cfg: dict) -> Entity:
        name = str(cfg.get("name") or key)
        if component == "switch":
            return Entity(key, "switch", name)
        if component == "light":
            dimmable = bool(cfg.get("brightness_command_topic") or (cfg.get("schema") == "json" and cfg.get("brightness")))
            return Entity(key, "light", name, brightness=0 if dimmable else None, attrs={"can": []})
        if component == "binary_sensor":
            return Entity(key, "binary_sensor", name, device_class=cfg.get("device_class"))
        return Entity(key, "sensor", name, unit=cfg.get("unit_of_measurement"), device_class=cfg.get("device_class"))

    def _state(self, device_id: str, key: str, topic: str, raw: str) -> None:
        device = self.hub.devices.get(device_id)
        spec = self.specs.get((device_id, key))
        if device is None or spec is None:
            return
        entity = device.entities[key]
        if topic == spec.get("availability_topic") and topic != spec.get("state_topic"):
            device.available = raw == spec.get("payload_available", "online")
            self.hub.changed(device)
            return
        component = spec["component"]
        on = str(spec.get("state_on", spec.get("payload_on", "ON")))
        off = str(spec.get("state_off", spec.get("payload_off", "OFF")))
        if component == "light" and spec.get("schema") == "json" and topic == spec.get("state_topic"):
            try:
                data = json.loads(raw)
            except ValueError:
                return
            entity.state = str(data.get("state", "")).upper() == "ON"
            if "brightness" in data:
                entity.brightness = round(data["brightness"] / int(spec.get("brightness_scale", 255)) * 100)
        elif component == "light" and topic == spec.get("brightness_state_topic"):
            value = extract(spec.get("brightness_value_template"), raw)
            try:
                entity.brightness = round(float(value) / int(spec.get("brightness_scale", 255)) * 100)
            except (TypeError, ValueError):
                return
        elif component in ("switch", "light", "binary_sensor"):
            value = str(extract(spec.get("value_template"), raw))
            if value.upper() == on.upper():
                entity.state = True
            elif value.upper() == off.upper():
                entity.state = False
            else:
                return
        else:
            value = extract(spec.get("value_template"), raw)
            if value is None:
                return
            try:
                entity.state = round(float(value), 2)
            except (TypeError, ValueError):
                entity.state = str(value)
        device.available, device.last_seen = True, time.time()
        self.hub.changed(device)

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool,
                      **extra) -> None:
        spec = self.specs.get((device.id, entity.key))
        if spec is None or self.client is None or not spec.get("command_topic"):
            raise RuntimeError(f"{device.name} cannot be controlled")
        want = (not entity.state) if toggle else on
        if brightness is not None:
            want = True
        if spec["component"] == "light" and spec.get("schema") == "json":
            body: dict = {}
            if want is not None:
                body["state"] = "ON" if want else "OFF"
            if brightness is not None:
                body["brightness"] = round(brightness / 100 * int(spec.get("brightness_scale", 255)))
            await self.client.publish(spec["command_topic"], json.dumps(body))
            return
        if want is not None:
            await self.client.publish(spec["command_topic"], str(spec.get("payload_on", "ON") if want else spec.get("payload_off", "OFF")))
        if brightness is not None and spec.get("brightness_command_topic"):
            await self.client.publish(spec["brightness_command_topic"], str(round(brightness / 100 * int(spec.get("brightness_scale", 255)))))
