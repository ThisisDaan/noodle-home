"""Light groups: several lamps shown and controlled as one light.

A group is a device "group:<id>" with one light entity. It is on when any member is on; its brightness is the
average of the members that are on. Turning it on, off or to a brightness sends that to every member; toggling
turns everything off when anything is on, otherwise everything on, so the lamps stay in step.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from ..hub import Device, Entity, Hub

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS light_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    members TEXT NOT NULL  -- JSON list of {"device_id", "key"}
);
"""


class GroupAdapter:
    source = "group"

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.db = hub.store.db
        self.db.executescript(SCHEMA)
        self.groups: dict[str, dict] = {
            row["id"]: {"id": row["id"], "name": row["name"], "members": json.loads(row["members"])}
            for row in self.db.execute("SELECT * FROM light_groups").fetchall()}
        hub.on_state_change(self._member_changed)

    async def run(self) -> None:
        await asyncio.sleep(5)  # let the member lamps load first
        for group in self.groups.values():
            self._publish(group)

    # --- managing groups (from the API)

    def save(self, name: str, members: list[dict], group_id: str | None = None) -> dict:
        group = {"id": group_id or uuid.uuid4().hex[:8], "name": name, "members": members}
        self.groups[group["id"]] = group
        self.db.execute("INSERT OR REPLACE INTO light_groups VALUES (?, ?, ?)",
                        (group["id"], name, json.dumps(members)))
        self.db.commit()
        meta = self.hub.store.device_meta(f"group:{group['id']}")
        if meta and meta.get("name"):  # the name set here wins over an older rename on the device page
            self.hub.store.set_device_meta(f"group:{group['id']}", None, meta.get("area"))
        self._publish(group)
        return group

    def delete(self, group_id: str) -> None:
        self.groups.pop(group_id, None)
        self.db.execute("DELETE FROM light_groups WHERE id = ?", (group_id,))
        self.db.commit()
        self.hub.remove(f"group:{group_id}")

    # --- state

    def _lamps(self, group: dict) -> list[Entity]:
        lamps = []
        for m in group["members"]:
            device = self.hub.devices.get(m["device_id"])
            if device and m["key"] in device.entities:
                lamps.append(device.entities[m["key"]])
        return lamps

    def _publish(self, group: dict) -> None:
        lamps = self._lamps(group)
        on = [e for e in lamps if e.state is True]
        levels = [e.brightness for e in (on or lamps) if e.brightness is not None]
        light = Entity("light", "light", "Light", state=bool(on) if lamps else None,
                       brightness=round(sum(levels) / len(levels)) if levels else None)
        device_id = f"group:{group['id']}"
        members = [self.hub.devices.get(m["device_id"]) for m in group["members"]]
        available = any(d and d.available for d in members)
        existing = self.hub.devices.get(device_id)
        if existing:
            existing.entities, existing.available = {"light": light}, available
            if not (self.hub.store.device_meta(device_id) or {}).get("name"):
                existing.name = group["name"]
            self.hub.changed(existing)
        else:
            self.hub.upsert(Device(id=device_id, source=self.source, name=group["name"], model="Light group",
                                   manufacturer="Noodle", available=available, entities={"light": light}))

    def _member_changed(self, device: Device, entity: Entity, old, new) -> None:
        for group in self.groups.values():
            if any(m["device_id"] == device.id and m["key"] == entity.key for m in group["members"]):
                self._publish(group)

    # --- control

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None,
                      toggle: bool) -> None:
        group = self.groups[device.id.split(":", 1)[1]]
        if toggle:
            on, toggle = not any(e.state is True for e in self._lamps(group)), False
        members = [m for m in group["members"] if m["device_id"] in self.hub.devices]
        results = await asyncio.gather(*(self.hub.command(m["device_id"], m["key"], on=on, brightness=brightness)
                                         for m in members), return_exceptions=True)
        for m, result in zip(members, results):
            if isinstance(result, Exception):
                log.warning("group %s: %s failed: %s", group["name"], m["device_id"], result)
