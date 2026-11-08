"""Matter via python-matter-server's WebSocket API.

Node attributes arrive as "endpoint/cluster/attribute" -> value. This adapter
turns the clusters it knows into entities and sends cluster commands back.
Switch-cluster events carry the real multi-press count (Home Assistant caps it
at the device's MultiPressMax, so fast wheel spins got lost there).
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import math
from typing import Any

import websockets

from ... import config
from ...hub import Device, Entity, Hub

log = logging.getLogger(__name__)

ON_OFF, LEVEL, DESCRIPTOR, BASIC, POWER_SOURCE = 6, 8, 29, 40, 47
ILLUMINANCE, OCCUPANCY, ELECTRICAL_POWER, SWITCH = 1024, 1030, 144, 59
LIGHT_DEVICE_TYPES = {256, 257, 268, 269}  # on/off, dimmable, color temperature, extended color
# Remotes whose inputs are better described than "Button 7". Keyed by the model name the device reports.
# Endpoints come in groups of `size` (e.g. profiles), `roles` names each input of a group in endpoint order as
# (name, device class: "wheel" if its clicks arrive as one counted press), and `show` is the order they are listed in.
REMOTE_LAYOUTS = {
    # Turning the wheel up is the first input of a profile and down the second (checked against a real remote:
    # flows send input 1 to "brighter" and input 2 to "dimmer"). They are listed down, up, button.
    "BILRESA": {"group": "Profile", "size": 3, "show": (1, 0, 2),
                "roles": (("Dimmer increase", "wheel"), ("Dimmer decrease", "wheel"), ("Button", None))},
}


def _layout(attrs: dict) -> dict | None:
    model = str(attrs.get(f"0/{BASIC}/3"))
    return next((v for k, v in REMOTE_LAYOUTS.items() if k in model), None)


SWITCH_EVENTS = {0: "switch_latched", 1: "initial_press", 2: "long_press", 3: "short_release",
                 4: "long_release", 5: "multi_press_ongoing", 6: "multi_press_complete"}


class MatterAdapter:
    source = "matter"

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.ws: Any = None
        self.server_info: dict = {}
        self.nodes: dict[int, dict] = {}
        self._ids = itertools.count(1)
        self._pending: dict[str, asyncio.Future] = {}

    @staticmethod
    def _id(node_id: int) -> str:
        return f"matter:{node_id}"

    async def run(self) -> None:
        while True:
            try:
                async with websockets.connect(config.MATTER_URL, max_size=None) as ws:
                    self.ws = ws
                    self.server_info = json.loads(await ws.recv())
                    log.info("connected to matter-server %s", config.MATTER_URL)
                    reader = asyncio.create_task(self._read(ws))
                    for node in await self.call("start_listening"):
                        self._load_node(node)
                    await reader  # returns or raises when the connection drops
            except Exception as err:
                log.warning("matter-server connection lost (%s), retrying in 5s", err)
            finally:
                self.ws = None
                for future in self._pending.values():
                    future.cancel()
                self._pending.clear()
            await asyncio.sleep(5)

    async def _read(self, ws) -> None:
        async for raw in ws:
            try:
                self._handle(json.loads(raw))
            except Exception:
                log.exception("bad matter-server message")

    async def call(self, command: str, **args: Any) -> Any:
        if not self.ws:
            raise RuntimeError("matter-server not connected")
        message_id = str(next(self._ids))
        future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        await self.ws.send(json.dumps({"message_id": message_id, "command": command, "args": args}))
        return await asyncio.wait_for(future, timeout=300)

    def _handle(self, msg: dict) -> None:
        if "message_id" in msg and msg["message_id"] in self._pending:
            future = self._pending.pop(msg["message_id"])
            if "error_code" in msg:
                future.set_exception(RuntimeError(f"{msg.get('error_code')}: {msg.get('details')}"))
            else:
                future.set_result(msg.get("result"))
            return
        event, data = msg.get("event"), msg.get("data")
        if event in ("node_added", "node_updated"):
            self._load_node(data)
        elif event == "node_removed":
            self.nodes.pop(data, None)
            self.hub.remove(self._id(data))
        elif event == "attribute_updated":
            node_id, path, value = data
            if node_id in self.nodes:
                self.nodes[node_id]["attributes"][path] = value
                self._refresh(node_id)
        elif event == "node_event":
            self._switch_event(data)

    def _load_node(self, node: dict) -> None:
        self.nodes[node["node_id"]] = node
        self._refresh(node["node_id"], new=True)

    def _refresh(self, node_id: int, new: bool = False) -> None:
        node = self.nodes[node_id]
        attrs = node["attributes"]
        device_id = self._id(node_id)
        existing = self.hub.devices.get(device_id)
        device = Device(
            id=device_id,
            source=self.source,
            name=attrs.get(f"0/{BASIC}/5") or attrs.get(f"0/{BASIC}/3") or f"Matter node {node_id}",
            model=attrs.get(f"0/{BASIC}/3"),
            manufacturer=attrs.get(f"0/{BASIC}/1"),
            available=bool(node.get("available", True)),
            entities=self._entities(attrs),
        )
        battery = attrs.get(f"0/{POWER_SOURCE}/12")  # BatPercentRemaining, in half percent
        device.battery = round(battery / 2) if isinstance(battery, int) else None
        if existing:  # button entities only get state from events: keep the last one
            for key, entity in device.entities.items():
                if entity.kind == "button" and key in existing.entities:
                    entity.state = existing.entities[key].state
        if new or not existing:
            self.hub.upsert(device)
        else:
            existing.available, existing.battery, existing.entities = device.available, device.battery, device.entities
            self.hub.changed(existing)

    def _entities(self, attrs: dict[str, Any]) -> dict[str, Entity]:
        endpoints: dict[int, dict[int, dict[int, Any]]] = {}
        for path, value in attrs.items():
            ep, cluster, attr = (int(x) for x in path.split("/"))
            endpoints.setdefault(ep, {}).setdefault(cluster, {})[attr] = value
        layout = _layout(attrs)
        entities: dict[str, Entity] = {}
        for ep, clusters in sorted(endpoints.items()):
            if ep == 0:
                continue
            types = {d.get("0") for d in clusters.get(DESCRIPTOR, {}).get(0, []) or []}
            suffix = f"_{ep}"
            if ON_OFF in clusters:
                is_light = bool(types & LIGHT_DEVICE_TYPES)
                level = clusters.get(LEVEL, {}).get(0)
                kind = "light" if is_light else "switch"
                entities[kind + suffix] = Entity(
                    key=kind + suffix, kind=kind, name=kind.capitalize(),
                    state=bool(clusters[ON_OFF].get(0)),
                    brightness=round(level / 254 * 100) if is_light and isinstance(level, int) else None,
                )
            if OCCUPANCY in clusters:
                entities["occupancy" + suffix] = Entity(
                    key="occupancy" + suffix, kind="binary_sensor", name="Motion", device_class="occupancy",
                    state=bool((clusters[OCCUPANCY].get(0) or 0) & 1))
            if ILLUMINANCE in clusters:
                raw = clusters[ILLUMINANCE].get(0)
                lux = round(10 ** ((raw - 1) / 10000)) if isinstance(raw, int) and raw > 0 else 0
                entities["illuminance" + suffix] = Entity(
                    key="illuminance" + suffix, kind="sensor", name="Illuminance", device_class="illuminance",
                    unit="lx", state=lux)
            if ELECTRICAL_POWER in clusters:
                milliwatts = clusters[ELECTRICAL_POWER].get(8)
                entities["power" + suffix] = Entity(
                    key="power" + suffix, kind="sensor", name="Power", device_class="power", unit="W",
                    state=round(milliwatts / 1000, 1) if isinstance(milliwatts, (int, float)) else None)
            if SWITCH in clusters:
                name, device_class, group = f"Button {ep}", None, None
                if layout:
                    role = layout["roles"][(ep - 1) % layout["size"]]
                    name, device_class = role
                    group = f"{layout['group']} {(ep - 1) // layout['size'] + 1}"
                entities["button" + suffix] = Entity(key="button" + suffix, kind="button", name=name,
                                                     device_class=device_class, group=group,
                                                     actions=self._switch_actions(clusters[SWITCH].get(65532)))
        if layout:
            def order(item: tuple[str, Entity]) -> tuple[int, int]:
                ep = int(item[0].rsplit("_", 1)[1])
                return (ep - 1) // layout["size"], layout["show"][(ep - 1) % layout["size"]]
            entities = dict(sorted(entities.items(), key=order))
        return entities

    @staticmethod
    def _switch_actions(features: int | None) -> list[str]:
        """The presses a Matter button reports, from its feature map (bit 3: long press, bit 4: multi press)."""
        if not isinstance(features, int):
            return ["multi_press", "long_press", "long_release"]
        return (["multi_press"] if features & 16 else []) + (["long_press", "long_release"] if features & 8 else [])

    def _switch_event(self, data: dict) -> None:
        if data.get("cluster_id") != SWITCH:
            return
        device = self.hub.devices.get(self._id(data["node_id"]))
        entity = device.entities.get(f"button_{data['endpoint_id']}") if device else None
        name = SWITCH_EVENTS.get(data.get("event_id"))
        if not entity or name not in ("long_press", "long_release", "multi_press_complete"):
            return
        count = 1
        if name == "multi_press_complete":
            count = (data.get("data") or {}).get("totalNumberOfPressesCounted", 1)
            entity.state = f"multi_press_{count}"
        else:
            entity.state = name
        self.hub.changed(device)
        # Rules match on "multi_press" (with the real count) or "long_press"/"long_release".
        self.hub.event(device, entity.key, "multi_press" if name == "multi_press_complete" else name,
                       {"count": count})

    async def commission(self, code: str, thread_dataset: str) -> dict:
        """Pair a new device over the Pi's Bluetooth with its QR or 11-digit code."""
        if not self.server_info.get("bluetooth_enabled"):
            raise RuntimeError("matter-server runs without Bluetooth (start it with --bluetooth-adapter 0)")
        await self.call("set_thread_dataset", dataset=thread_dataset)
        node = await self.call("commission_with_code", code=code, network_only=False)
        self._load_node(node)
        return node

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool) -> None:
        node_id = int(device.id.split(":", 1)[1])
        endpoint = int(entity.key.rsplit("_", 1)[1])
        if brightness is not None and entity.kind == "light":
            level = max(1, min(254, math.ceil(brightness / 100 * 254)))
            await self.call("device_command", node_id=node_id, endpoint_id=endpoint, cluster_id=LEVEL,
                            command_name="MoveToLevelWithOnOff",
                            payload={"level": level, "transitionTime": 3, "optionsMask": 0, "optionsOverride": 0})
            return
        command = "Toggle" if toggle else ("On" if on else "Off")
        await self.call("device_command", node_id=node_id, endpoint_id=endpoint, cluster_id=ON_OFF,
                        command_name=command, payload={})
