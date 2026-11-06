"""Combined devices: several devices shown and controlled as one (see templates.py).

A combined device is a file `<config>/combined/<id>.yaml` and a device "combined:<id>". The work is done by an
ordinary flow `combined-<id>` that the template writes, so it can be opened and read like any other. The flow is
switched on only while the combined device is on (heating), and it is rewritten whenever its settings change.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid

from ... import config, flowfiles
from ...hub import Device, Entity, Hub
from ...yamlfile import YamlFile
from .templates import TEMPLATES

log = logging.getLogger(__name__)


class CombinedAdapter:
    source = "combined"
    extra_commands = ("value", "mode")

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.dir = config.CONFIG_DIR / "combined"
        self.engine = None  # the FlowEngine, attached by main once it exists
        self.items: dict[str, dict] = {}
        self._stamps: dict[str, tuple[int, int]] = {}  # file name -> (mtime, size) we last read or wrote
        for path in sorted(self.dir.glob("*.yaml")) if self.dir.is_dir() else []:
            self._read(path)
        hub.on_state_change(self._member_changed)

    def attach_flows(self, engine) -> None:
        self.engine = engine

    async def run(self) -> None:
        await asyncio.sleep(5)  # let the member devices load first
        for item in self.items.values():
            self._publish(item)
        while True:  # the files can be edited by hand: pick up a change within a few seconds (no network, just stat)
            await asyncio.sleep(3)
            try:
                self.reload()
            except Exception:
                log.exception("checking the combined files failed")

    # --- the files

    @staticmethod
    def _stamp(path) -> tuple[int, int]:
        st = path.stat()
        return st.st_mtime_ns, st.st_size

    def _read(self, path) -> dict | None:
        """Read one file into `items` if it is a valid combined device; say why not in the log otherwise."""
        try:
            self._stamps[path.name] = self._stamp(path)
            item = YamlFile(path).read()
            tpl = TEMPLATES.get(item.get("template"))
            if tpl is None or not item.get("id"):
                raise ValueError("unknown template or no id")
            item["id"] = str(item["id"])
            item["values"] = tpl.clean(item.get("values") or {})
            item["enabled"] = True if tpl.always_on else bool(item.get("enabled"))
            errors = [e for e in tpl.validate(item["values"], self.hub.devices) if "known device" not in e]
            if errors:
                raise ValueError("; ".join(errors))
        except Exception as err:
            log.warning("combined device file %s ignored: %s", path.name, err)
            return None
        self.items[item["id"]] = item
        return item

    def reload(self) -> None:
        """Apply files that changed or were removed since we last looked (our own writes are not changes)."""
        if not self.dir.is_dir():
            return
        files = {p.name: p for p in self.dir.glob("*.yaml")}
        for name, path in files.items():
            if self._stamps.get(name) != self._stamp(path):
                item = self._read(path)
                if item:
                    log.info("combined device %s changed in its file", item["id"])
                    self._sync_flow(item)
                    self._publish(item)
        for name in [n for n in self._stamps if n not in files]:
            del self._stamps[name]
            cid = name.removesuffix(".yaml")
            if cid in self.items:
                self.delete(cid)

    # --- managing (from the API)

    def save(self, template: str, name: str, values: dict, cid: str | None = None) -> dict:
        tpl = TEMPLATES.get(template)
        if tpl is None:
            raise ValueError("Unknown template")
        name = name.strip()
        if not name:
            raise ValueError("Give it a name")
        values = tpl.clean(values)
        errors = tpl.validate(values, self.hub.devices)
        if errors:
            raise ValueError("; ".join(errors))
        cid = cid or uuid.uuid4().hex[:8]
        if not re.fullmatch(r"[0-9a-z]+", cid):
            raise ValueError("Bad id")
        old = self.items.get(cid)
        item = {"id": cid, "name": name, "template": template,
                "enabled": True if tpl.always_on else bool(old and old.get("enabled")), "values": values}
        self.items[cid] = item
        self.dir.mkdir(parents=True, exist_ok=True)
        self._write(item)
        self._sync_flow(item)
        self._publish(item)
        return item

    def _write(self, item: dict) -> None:
        path = self.dir / f"{item['id']}.yaml"
        YamlFile(path).write(item, replace=True)
        self._stamps[path.name] = self._stamp(path)

    def delete(self, cid: str) -> None:
        item = self.items.pop(cid, None)
        if item is None:
            return
        (self.dir / f"{cid}.yaml").unlink(missing_ok=True)
        self._stamps.pop(f"{cid}.yaml", None)
        if self.engine and f"combined-{cid}" in self.engine.flows:
            self.engine.delete(f"combined-{cid}")
        self.hub.remove(f"combined:{cid}")

    def _sync_flow(self, item: dict) -> None:
        """Write the flow for this device (if its template has one), switched on only while the device is on."""
        if self.engine is None:
            return
        doc = TEMPLATES[item["template"]].flow(item["id"], item["name"], item["values"])
        flow_id = f"combined-{item['id']}"
        if doc is None:
            if flow_id in self.engine.flows:
                self.engine.delete(flow_id)
            return
        flow = flowfiles.from_doc(doc)
        if flow_id in self.engine.flows:
            self.engine.update(flow_id, name=flow["name"], graph=flow["graph"], enabled=bool(item["enabled"]))
        else:
            self.engine.create(flow["name"], flow["graph"], enabled=bool(item["enabled"]), flow_id=flow_id)

    def set_enabled(self, item: dict, enabled: bool) -> None:
        item["enabled"] = enabled
        self._write(item)
        self._sync_flow(item)
        self._publish(item)

    # --- state

    def _publish(self, item: dict) -> None:
        tpl = TEMPLATES[item["template"]]
        device_id = f"combined:{item['id']}"
        existing = self.hub.devices.get(device_id)
        old = next(iter(existing.entities.values()), None) if existing else None
        entity = tpl.entity(item, self.hub, old)
        members = [self.hub.devices.get(d) for d, _ in tpl.members(item["values"])]
        available = all(m is not None and m.available for m in members)  # a missing member: shown as offline
        if existing:
            existing.entities, existing.available = {entity.key: entity}, available
            if not (self.hub.store.device_meta(device_id) or {}).get("name"):
                existing.name = item["name"]
            self.hub.changed(existing)
        else:
            self.hub.upsert(Device(id=device_id, source=self.source, name=item["name"], model=tpl.model,
                                   manufacturer="Noodle", available=available, entities={entity.key: entity}))

    def _member_changed(self, device: Device, entity: Entity, old, new) -> None:
        for item in list(self.items.values()):
            if (device.id, entity.key) in TEMPLATES[item["template"]].members(item["values"]):
                self._publish(item)

    # --- control

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None,
                      toggle: bool, **extra) -> None:
        item = self.items[device.id.split(":", 1)[1]]
        await TEMPLATES[item["template"]].command(self, item, on, toggle, extra)
