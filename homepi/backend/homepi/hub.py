"""Device registry shared by all adapters, the API and live updates.

A device has entities; each entity is one thing you can see or control:
  light          state (bool), brightness (0-100 or None)
  switch         state (bool)
  binary_sensor  state (bool), device_class (occupancy, contact, presence)
                 Every motion sensor also gets a "presence" entity: on with motion, and it stays on until there
                 has been no motion for the sensor's presence minutes (a built-in timer).
  sensor         state (number/str), unit, device_class
  button         state (last action, e.g. "single" or "multi_press_3"), actions (the presses it can send)
  number         state (a settable value, e.g. a thermostat target), unit
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from .store import Store

log = logging.getLogger(__name__)

DEFAULT_PRESENCE_MINUTES = 5.0


@dataclass
class Entity:
    key: str
    kind: str
    name: str
    state: Any = None
    brightness: int | None = None
    unit: str | None = None
    device_class: str | None = None
    actions: list[str] | None = None  # buttons: what this button can send, e.g. ["single", "double", "hold"]
    group: str | None = None  # inputs that belong together, e.g. one profile of a multi-profile remote


@dataclass
class Device:
    id: str
    source: str
    name: str
    model: str | None = None
    manufacturer: str | None = None
    available: bool = True
    battery: int | None = None
    area: str | None = None
    last_seen: float | None = None
    presence_minutes: float | None = None  # motion sensors only
    entities: dict[str, Entity] = field(default_factory=dict)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["entities"] = [asdict(e) for e in self.entities.values()]
        return data


class Adapter(Protocol):
    source: str

    async def run(self) -> None: ...

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool) -> None: ...


StateListener = Callable[[Device, Entity, Any, Any], None]
EventListener = Callable[[Device, str, str, dict], None]


class Hub:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.devices: dict[str, Device] = {}
        self.adapters: dict[str, Adapter] = {}
        self._listeners: set[Callable[[dict], Awaitable[None]]] = set()
        # For automations: per-entity state changes and button events.
        self._state_listeners: list[StateListener] = []
        self._event_listeners: list[EventListener] = []
        self._known: dict[tuple[str, str], Any] = {}
        self._since: dict[tuple[str, str], float] = {}
        self.loop: asyncio.AbstractEventLoop | None = None  # set at startup; see spawn()
        self._presence_due: dict[str, float] = {}  # device id -> when its presence runs out

    def spawn(self, coro: Awaitable) -> None:
        """Start background work. Works from the event loop and from the API's worker threads (plain `def`
        endpoints run there, where asyncio.create_task fails with "no running event loop")."""
        try:
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            if self.loop is None:
                coro.close()  # not started yet: nothing can run it
            else:
                self.loop.call_soon_threadsafe(self.loop.create_task, coro)

    def on_state_change(self, listener: StateListener) -> None:
        self._state_listeners.append(listener)

    def on_event(self, listener: EventListener) -> None:
        self._event_listeners.append(listener)

    def event(self, device: Device, key: str, action: str, data: dict | None = None) -> None:
        """Adapters call this for momentary things like button presses."""
        self._record(device, key, action)
        for listener in self._event_listeners:
            listener(device, key, action, data or {})

    def _record(self, device: Device, key: str, value) -> None:
        """Store a history row and push it to the open pages, so graphs grow without asking again."""
        ts = self.store.add_history(device.id, key, value)
        if ts is not None:
            self.broadcast({"type": "history", "device_id": device.id, "key": key, "ts": ts, "value": value})

    def since(self, device_id: str, key: str) -> float | None:
        """Unix time since which the entity has had its current state."""
        return self._since.get((device_id, key))

    def _track(self, device: Device) -> None:
        now = time.time()
        for entity in device.entities.values():
            if entity.key != "presence":
                self._track_entity(device, entity, now)
        # Presence follows from the motion state and how long it has had it, so it is tracked last.
        presence = self._presence(device, now)
        if presence:
            self._track_entity(device, presence, now)

    def _track_entity(self, device: Device, entity: Entity, now: float) -> None:
        if entity.kind == "button":
            return
        ident = (device.id, entity.key)
        if entity.state is None:
            # Known entity, unknown state (e.g. Zigbee sensors until their first report).
            self._known.setdefault(ident, None)
            return
        value = (entity.state, entity.brightness)
        old = self._known.get(ident, ...)
        if old is None:
            # First report after unknown: for sensors that is a real event (motion, mailbox opened);
            # for lights and switches it is only the state sync at startup.
            old = (None, None) if entity.kind == "binary_sensor" else ...
        if old == value:
            return
        self._known[ident] = value
        if old is ... or old[0] != entity.state:
            # Keep the stored "since" when the state is unchanged across a restart.
            stored = self.store.since(device.id, entity.key)
            if old is ... and stored and stored[0] == repr(entity.state):
                self._since[ident] = stored[1]
            else:
                self._since[ident] = now
                self.store.set_since(device.id, entity.key, repr(entity.state), now)
        if old is ...:
            return  # first sighting is not a change
        if old[0] != entity.state:
            self._record(device, entity.key, entity.state)
        for listener in self._state_listeners:
            listener(device, entity, old[0], entity.state)

    def _presence(self, device: Device, now: float) -> Entity | None:
        """Add or update the presence entity of a motion sensor. Returns it, or None for other devices."""
        motion = next((e for e in device.entities.values() if e.device_class == "occupancy"), None)
        if motion is None:
            return None
        minutes = self.store.presence_minutes(device.id)
        device.presence_minutes = DEFAULT_PRESENCE_MINUTES if minutes is None else minutes
        presence = device.entities.get("presence")
        if presence is None:
            presence = device.entities["presence"] = Entity(
                key="presence", kind="binary_sensor", name="Presence", device_class="presence")
        known = self._known.get((device.id, "presence"))
        was = known[0] if isinstance(known, tuple) else None
        stopped = self._since.get((device.id, motion.key)) or now
        due = stopped + device.presence_minutes * 60
        if motion.state is None:
            presence.state = None
        elif motion.state:
            presence.state = True
        elif was is False or (was is None and stopped >= now):
            presence.state = False  # only motion makes a room occupied; a new sensor starts empty
        else:
            # Motion stopped: present until the minutes have passed since then (counts on across restarts).
            presence.state = now < due
            if presence.state and self._presence_due.get(device.id) != due:
                self._presence_due[device.id] = due
                self.spawn(self._presence_timer(device.id, due))
        return presence

    async def _presence_timer(self, device_id: str, due: float) -> None:
        await asyncio.sleep(max(0.0, due - time.time()) + 0.05)
        device = self.devices.get(device_id)
        if device is None or self._presence_due.get(device_id) != due:
            return  # motion came back or the minutes changed: another timer is in charge
        self._presence_due.pop(device_id, None)
        self.changed(device)

    def register(self, adapter: Adapter) -> None:
        self.adapters[adapter.source] = adapter

    # listeners get {"type": "device", "device": {...}} or {"type": "removed", "id": ...}
    def subscribe(self, listener: Callable[[dict], Awaitable[None]]) -> None:
        self._listeners.add(listener)

    def unsubscribe(self, listener: Callable[[dict], Awaitable[None]]) -> None:
        self._listeners.discard(listener)

    def broadcast(self, message: dict) -> None:
        for listener in list(self._listeners):
            self.spawn(self._safe_send(listener, message))

    async def _safe_send(self, listener, message: dict) -> None:
        try:
            await listener(message)
        except Exception:  # a closed websocket: drop it
            self._listeners.discard(listener)

    def upsert(self, device: Device) -> None:
        """Adapters call this with the device as the source sees it; local name/area win."""
        meta = self.store.device_meta(device.id)
        if meta is None:
            meta = {"name": None, "area": self._guess_area(device.name)}
            self.store.set_device_meta(device.id, None, meta["area"], defer=True)
        if meta.get("name"):
            device.name = meta["name"]
        device.area = meta.get("area")
        device.last_seen = device.last_seen or time.time()
        self.devices[device.id] = device
        self._track(device)
        self.broadcast({"type": "device", "device": device.as_dict()})

    def remove(self, device_id: str) -> None:
        if self.devices.pop(device_id, None):
            self.broadcast({"type": "removed", "id": device_id})

    def changed(self, device: Device) -> None:
        device.last_seen = time.time()
        self._track(device)
        self.broadcast({"type": "device", "device": device.as_dict()})

    def reapply_meta(self) -> None:
        """Names and rooms were edited in areas.yaml: show them on the devices that are here."""
        for device in self.devices.values():
            meta = self.store.device_meta(device.id)
            if not meta:
                continue
            name, area = meta.get("name") or device.name, meta.get("area")
            if (name, area) != (device.name, device.area):
                device.name, device.area = name, area
                self.broadcast({"type": "device", "device": device.as_dict()})

    def _guess_area(self, name: str) -> str | None:
        lowered = name.lower()
        for area in self.store.areas():
            if lowered.startswith(area.lower()):
                return area
        return None

    def set_meta(self, device_id: str, name: str | None, area: str | None,
                 presence_minutes: float | None = None) -> Device:
        device = self.devices[device_id]
        self.store.set_device_meta(device_id, name or None, area or None)
        if presence_minutes is not None and device.presence_minutes is not None:
            self.store.set_presence_minutes(device_id, presence_minutes)
        if name:
            device.name = name
        device.area = area or None
        self.changed(device)
        return device

    def set_presence_minutes(self, device_id: str, minutes: float) -> Device:
        device = self.devices[device_id]
        if device.presence_minutes is None:
            raise ValueError(f"{device.name} is not a motion sensor")
        self.store.set_presence_minutes(device_id, minutes)
        self.changed(device)  # works out presence again with the new minutes
        return device

    async def command(self, device_id: str, key: str, on: bool | None = None,
                      brightness: int | None = None, toggle: bool = False, value: float | None = None) -> None:
        device = self.devices[device_id]
        entity = device.entities[key]
        if entity.kind not in ("light", "switch", "number"):
            raise ValueError(f"{entity.kind} cannot be controlled")
        adapter = self.adapters[device.source]
        if entity.kind == "number":
            await adapter.command(device, entity, on, brightness, toggle, value=value)
        else:
            await adapter.command(device, entity, on, brightness, toggle)
