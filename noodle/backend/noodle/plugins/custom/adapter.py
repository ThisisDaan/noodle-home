"""Custom devices: devices you make yourself, whose fields flows write to and read from.

A custom device "custom:<id>" has fields, each shown as one entity: a switch (on/off), a number or text. A flow
fills them with the "Write to entity" step, and everything that works with a device works with them: the Devices
page, "Device changes", checks, the dashboard. The old flow variables live here too, as the text fields of the
built-in "Variables" device (see `_migrate_variables`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from ...hub import Device, Entity, Hub

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS custom_devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    fields TEXT NOT NULL  -- JSON list of {"key", "label", "type": "switch" | "number" | "text", "unit"}
);
CREATE TABLE IF NOT EXISTS custom_values (
    device_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated REAL NOT NULL,
    PRIMARY KEY (device_id, key)
);
"""

TYPES = ("switch", "number", "text")
VARIABLES_ID = "variables"  # the built-in device that holds the flow variables
ON_WORDS = ("on", "true", "yes", "1")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "field"


class CustomAdapter:
    source = "custom"
    extra_commands = ("value",)

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.db = hub.store.db
        self.db.executescript(SCHEMA)
        self.devices: dict[str, dict] = {
            row["id"]: {"id": row["id"], "name": row["name"], "fields": json.loads(row["fields"])}
            for row in self.db.execute("SELECT * FROM custom_devices").fetchall()}
        self._migrate_variables()

    async def run(self) -> None:
        for device in self.devices.values():
            self._publish(device)

    # --- the old variables become the text fields of one device

    def _migrate_variables(self) -> None:
        """Move the flow variables into the "Variables" device. The old table is left as it is, nothing is
        deleted, and a variable that is already a field (and its newer value) is never overwritten, so this is
        safe to run on every start."""
        try:
            old = self.db.execute("SELECT name, value, updated FROM variables").fetchall()
        except Exception:  # a database that never had variables
            old = []
        if not old and VARIABLES_ID not in self.devices:
            return
        device = self._variables_device()
        changed = False
        for row in old:
            if not any(f["key"] == row["name"] for f in device["fields"]):
                device["fields"].append({"key": row["name"], "label": row["name"], "type": "text"})
                changed = True
            if not self.db.execute("SELECT 1 FROM custom_values WHERE device_id = ? AND key = ?",
                                   (VARIABLES_ID, row["name"])).fetchone():
                self.db.execute("INSERT INTO custom_values VALUES (?, ?, ?, ?)",
                                (VARIABLES_ID, row["name"], row["value"], row["updated"]))
                changed = True
        if changed:
            self._store(device)
            self.db.commit()

    def _variables_device(self) -> dict:
        if VARIABLES_ID not in self.devices:
            self.devices[VARIABLES_ID] = {"id": VARIABLES_ID, "name": "Variables", "fields": []}
        return self.devices[VARIABLES_ID]

    # --- managing devices (from the API)

    @staticmethod
    def _field(raw: dict, taken: set[str]) -> dict:
        label, kind = str(raw.get("label", "")).strip(), raw.get("type")
        if not label or len(label) > 40:
            raise ValueError("Every field needs a name of up to 40 characters")
        if kind not in TYPES:
            raise ValueError("A field is a switch, a number or text")
        key = str(raw.get("key") or "")
        if not key:
            key = base = slug(label)
            for n in range(2, 100):
                if key not in taken:
                    break
                key = f"{base}_{n}"
        if key in taken:
            raise ValueError(f"Two fields are called {label}")
        taken.add(key)
        field = {"key": key, "label": label, "type": kind}
        if kind == "number":
            if str(raw.get("unit") or "").strip():
                field["unit"] = str(raw["unit"]).strip()[:10]
            for limit in ("min", "max", "step"):  # the range a dial or slider on the card uses
                value = raw.get(limit)
                if value is not None and value != "":
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise ValueError(f"{label}: {limit} must be a number")
                    field[limit] = value
            if "min" in field and "max" in field and field["min"] >= field["max"]:
                raise ValueError(f"{label}: the lowest must be below the highest")
            if field.get("step", 1) <= 0:
                raise ValueError(f"{label}: the step must be above 0")
        return field

    def save(self, name: str, fields: list[dict], device_id: str | None = None) -> dict:
        name = name.strip()
        if not name or len(name) > 60:
            raise ValueError("Give it a name of up to 60 characters")
        if len(fields) > 30:
            raise ValueError("A custom device can have up to 30 fields")
        if device_id is not None and device_id not in self.devices:
            raise KeyError(device_id)
        taken: set[str] = set()
        clean = [self._field(f, taken) for f in fields]
        device_id = device_id or uuid.uuid4().hex[:8]
        old = self.devices.get(device_id)
        device = {"id": device_id, "name": name, "fields": clean}
        for gone in [f for f in (old["fields"] if old else []) if f["key"] not in taken]:
            self.db.execute("DELETE FROM custom_values WHERE device_id = ? AND key = ?", (device_id, gone["key"]))
        self.devices[device_id] = device
        self._store(device)
        self.db.commit()
        meta = self.hub.store.device_meta(f"custom:{device_id}")
        if meta and meta.get("name"):  # the name set here wins over an older rename on the device page
            self.hub.store.set_device_meta(f"custom:{device_id}", None, meta.get("area"))
        self._publish(device)
        return self.describe(device)

    def delete(self, device_id: str) -> None:
        if device_id == VARIABLES_ID:
            raise ValueError("The Variables device is built in")
        if self.devices.pop(device_id, None) is None:
            raise KeyError(device_id)
        self.db.execute("DELETE FROM custom_devices WHERE id = ?", (device_id,))
        self.db.execute("DELETE FROM custom_values WHERE device_id = ?", (device_id,))
        self.db.commit()
        self.hub.remove(f"custom:{device_id}")

    def describe(self, device: dict) -> dict:
        return {"id": device["id"], "name": device["name"], "fields": device["fields"],
                "builtin": device["id"] == VARIABLES_ID}

    def listing(self) -> list[dict]:
        return [self.describe(d) for d in self.devices.values()]

    def _store(self, device: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO custom_devices VALUES (?, ?, ?)",
                        (device["id"], device["name"], json.dumps(device["fields"])))

    # --- values

    def _raw(self, device_id: str, key: str) -> tuple[str, float] | None:
        row = self.db.execute("SELECT value, updated FROM custom_values WHERE device_id = ? AND key = ?",
                              (device_id, key)).fetchone()
        return (row["value"], row["updated"]) if row else None

    @staticmethod
    def _typed(field: dict, raw: str | None) -> Any:
        if raw is None:
            return False if field["type"] == "switch" else None
        if field["type"] == "switch":
            return raw == "on"
        if field["type"] == "number":
            try:
                return float(raw)
            except ValueError:
                return None
        return raw

    def write(self, device_id: str, key: str, value: Any) -> Any:
        """Set a field, from a flow or the interface. The value is made to fit the field: a switch takes on / off /
        true / false, a number must be a number, text is text. Raises KeyError for an unknown device or field and
        ValueError for a value that does not fit."""
        device = self.devices.get(device_id)
        field = next((f for f in device["fields"] if f["key"] == key), None) if device else None
        if field is None:
            raise KeyError(f"{device_id}.{key}")
        if field["type"] == "switch":
            on = value if isinstance(value, bool) else str(value).strip().lower() in ON_WORDS
            stored, typed = ("on" if on else "off"), on
        elif field["type"] == "number":
            if isinstance(value, bool):
                raise ValueError(f"{field['label']} needs a number")
            try:
                typed = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{field['label']} needs a number, not {value!r}") from None
            stored = repr(typed)
        else:
            typed = stored = str(value)
        self.db.execute("INSERT OR REPLACE INTO custom_values VALUES (?, ?, ?, ?)", (device_id, key, stored, time.time()))
        self.db.commit()
        self._publish(device)
        return typed

    # --- the flow variables (see the "Set variable" and "Check variable" steps)

    def set_variable(self, name: str, value: str) -> None:
        device = self._variables_device()
        if not any(f["key"] == name for f in device["fields"]):
            device["fields"].append({"key": name, "label": name, "type": "text"})
            self._store(device)
        self.write(VARIABLES_ID, name, value)

    def get_variable(self, name: str) -> str | None:
        raw = self._raw(VARIABLES_ID, name)
        return raw[0] if raw else None

    def variables(self) -> dict[str, dict]:
        device = self.devices.get(VARIABLES_ID)
        if not device:
            return {}
        out = {}
        for f in sorted(device["fields"], key=lambda f: f["key"]):
            raw = self._raw(VARIABLES_ID, f["key"])
            if raw:
                out[f["key"]] = {"value": raw[0], "updated": raw[1]}
        return out

    # --- the device in the hub

    def _publish(self, device: dict) -> None:
        entities: dict[str, Entity] = {}
        for f in device["fields"]:
            raw = self._raw(device["id"], f["key"])
            state = self._typed(f, raw[0] if raw else None)
            kind = {"switch": "switch", "number": "number", "text": "sensor"}[f["type"]]
            entities[f["key"]] = Entity(f["key"], kind, f["label"], state=state, unit=f.get("unit"),
                                        attrs={k: f[k] for k in ("min", "max", "step") if k in f})
        device_id = f"custom:{device['id']}"
        existing = self.hub.devices.get(device_id)
        if existing:
            existing.entities = entities
            if not (self.hub.store.device_meta(device_id) or {}).get("name"):
                existing.name = device["name"]
            self.hub.changed(existing)
        else:
            self.hub.upsert(Device(id=device_id, source=self.source, name=device["name"],
                                   model="Variables" if device["id"] == VARIABLES_ID else "Custom device",
                                   manufacturer="Noodle", entities=entities))

    # --- control (the Devices page and the dashboard can switch and set fields too)

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None,
                      toggle: bool, **extra) -> None:
        device_id = device.id.split(":", 1)[1]
        if entity.kind == "switch":
            self.write(device_id, entity.key, (not entity.state) if toggle else bool(on))
        elif entity.kind == "number" and extra.get("value") is not None:
            self.write(device_id, entity.key, extra["value"])
