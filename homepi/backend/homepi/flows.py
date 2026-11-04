"""Visual flows: a graph of trigger, condition and action nodes, edited in the web UI.

A flow is {"nodes": [{id, type, data, position}], "edges": [{source, sourceHandle, target}]}.
When a trigger node fires, a message travels along the edges (an edge's targetHandle picks the input
of nodes that have more than one):

  trigger.state     a device changed             data: device_id, outputs: the ticked "<entity>:on" / "<entity>:off"
                    (numeric entities: "<entity>:out"), each its own output, e.g. ["occupancy:on", "presence:off"]
  trigger.event     a button press               data: device_id, outputs: the ticked "<button>:<press>", each its
                    own output, e.g. ["action:single", "action:double"] ("<button>:*" = any press)
  trigger.thermostat  a temperature crosses a target  data: device_id, key, target, margin; outputs "cold"
                    (at or below target - margin) / "warm" (at or above target + margin), once per crossing;
                    input "check": a message arriving there re-reads the temperature and takes the matching output now
                    (nothing happens between the limits)
  trigger.time      every day at a time          data: at ("HH:MM")
  trigger.interval  every N seconds              data: seconds
  cond.state        entity is on/off             outputs "on" / "off"; with op =/>/< (numbers): "yes" / "no"
  cond.for          entity on/off for >= N min (survives restarts), or a value above/below a limit for >= N min
  cond.time         now between two times        outputs "yes" / "no"
  action.device     one input per ticked action: on/off/toggle/brightness/brighter/dimmer  data: inputs
                    (brighter/dimmer use the press count)
  action.cycle      sends the next of a list of messages as msg.payload  data: steps [{...}], inputs
                    "next" / "back" stop at the ends, "loop" goes forward and wraps; the position survives restarts
  action.repeat     inputs "start" / "stop": sends the message on every N seconds until stopped  data: seconds, max_seconds
  action.device     also "loop_start" / "loop_stop": cycles a light through brightness levels until stopped or timed out
                    data: loop_levels [25, 50, ...] (0 = off), loop_seconds per step, loop_max_seconds
  (action.device also has a "message" input: msg.payload {brightness} / {on} / {toggle} is applied to the device)
  action.delay      wait N seconds
  action.timer     countdown with two inputs: "start" and "stop"; continues when it runs out
                    data: minutes, restart (true: a new start begins again; false: keep the running one)
  action.log        write a line to the flow log
  (action.notify and action.speak are added by plugins, see plugins/notifications.py and plugins/speak.py;
   integrations can add more nodes with Plugin.nodes())
  action.var        set a variable               data: name, value
  cond.var          variable equals / differs    data: name, op ("eq"|"neq"), value
  trigger.webhook   POST /api/hook/<token>/<name> (e.g. from a notification button)  data: name
  trigger.sun       at sunrise or sunset          data: event ("sunrise"|"sunset"), offset (minutes, - = before)
  trigger.manual    the Run button of the flow (and the "Run flow" action of other flows)
  trigger.time      also data: days [0-6, Monday = 0]; none = every day
  cond.day          today is one of data: days
  cond.dark         the sun is down            outputs "yes" / "no"
  action.throttle   lets a message through at most once per data: minutes
  action.http       call a URL                   data: url, method, body
  action.flow       run the manual triggers of another flow  data: flow_id

Texts may use {count} (button presses), {temperature} (from a thermostat) and {now} (current date and time).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timedelta
from typing import Any

import httpx

from . import config, flowfiles, plugins, sun
from .hub import Device, Entity, Hub
from .store import Store

log = logging.getLogger(__name__)


def _fill(text: Any, msg: dict) -> str:
    return (str(text or "").replace("{count}", str(msg.get("count", "")))
            .replace("{temperature}", str(msg.get("temperature", "")))
            .replace("{now}", datetime.now().strftime("%d-%m %H:%M")))

def stack_graphs(graphs: list[dict]) -> tuple[dict, list[dict[str, str]]]:
    """Put several flow graphs under each other in one graph. Node ids that are already taken get a number.
    Returns the graph and, per input graph, which node ids were renamed."""
    nodes: list[dict] = []
    edges: list[dict] = []
    renames: list[dict[str, str]] = []
    bottom = None
    for g in graphs:
        taken = {n["id"] for n in nodes}
        rename = {}
        for n in g.get("nodes", []):
            new, i = n["id"], 2
            while new in taken:
                new, i = f"{n['id']}{i}", i + 1
            taken.add(new)
            if new != n["id"]:
                rename[n["id"]] = new
        ys = [n["position"]["y"] for n in g.get("nodes", [])] or [0]
        shift = 0 if bottom is None else bottom + 260 - min(ys)  # leave room below the part above
        for n in g.get("nodes", []):
            nodes.append({**n, "id": rename.get(n["id"], n["id"]),
                          "position": {"x": n["position"]["x"], "y": n["position"]["y"] + shift}})
        for e in g.get("edges", []):
            src, dst = rename.get(e["source"], e["source"]), rename.get(e["target"], e["target"])
            edges.append({**e, "source": src, "target": dst, "id": f"{src}-{e.get('sourceHandle') or 'out'}-{dst}"
                          + (f"-{e['targetHandle']}" if e.get("targetHandle") else "")})
        bottom = max(ys) + shift
        renames.append(rename)
    return {"nodes": nodes, "edges": edges}, renames


SCHEMA = """
CREATE TABLE IF NOT EXISTS flows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    graph TEXT NOT NULL,
    last_run REAL,
    last_error TEXT,
    updated REAL NOT NULL
);
-- Running countdowns of action.timer nodes (name = node id); survive restarts.
CREATE TABLE IF NOT EXISTS flow_timers (
    flow_id TEXT NOT NULL,
    name TEXT NOT NULL,
    node_id TEXT NOT NULL,
    deadline REAL NOT NULL,
    msg TEXT NOT NULL,
    PRIMARY KEY (flow_id, name)
);
"""
MAX_STEPS = 200


class NodeRun:
    """What a plugin's node gets to work with while it runs (see plugins.base.Node)."""

    def __init__(self, engine: "FlowEngine", flow: dict, node: dict, msg: dict, steps: list[int]) -> None:
        self._engine, self._flow, self._node, self._steps = engine, flow, node, steps
        self.msg, self.data = msg, node.get("data", {})
        self.store, self.hub = engine.store, engine.hub

    def fill(self, text: Any) -> str:
        """The text with {count}, {temperature} and {now} filled in."""
        return _fill(text, self.msg)

    def log(self, message: str) -> None:
        self._engine.add_log(self._flow["id"], message)

    async def follow(self, handle: str = "out") -> None:
        """Send the message on to whatever is connected to this output."""
        await self._engine._follow(self._flow, self._node, self.msg, handle, self._steps)


class FlowEngine:
    def __init__(self, hub: Hub, store: Store) -> None:
        self.hub, self.store = hub, store
        store.db.executescript(SCHEMA)
        self.flows: dict[str, dict] = {}
        self.logs: dict[str, deque] = {}
        self._fired_today: dict[tuple[str, str], str] = {}
        self._next_interval: dict[tuple[str, str], float] = {}
        self._past_since: dict[tuple, float] = {}
        self.timers: dict[tuple[str, str], dict] = {}
        self._repeats: dict[tuple[str, str], asyncio.Task] = {}
        self._loops: dict[tuple[str, str], asyncio.Task] = {}  # running brightness loops
        self.passed: dict[str, dict[str, float]] = {}
        self._throttled: dict[tuple[str, str], float] = {}  # action.throttle -> when it last let a message through
        self._zone: dict[tuple[str, str], str] = {}  # thermostat node -> "cold" / "warm" it last fired
        self._task: asyncio.Task | None = None
        self._watcher: asyncio.Task | None = None
        # The flows are YAML files (see flowfiles.py); the database keeps them as a copy and holds what the
        # files should not: when a flow last ran, its error, timers.
        self.files = flowfiles.FlowFiles(config.CONFIG_DIR / "flows")
        self.file_issues: dict[str, dict] = {}  # file name -> errors and warnings from checking it
        self._files_ready = False
        self._gone: set[str] = set()
        self._load()
        self._load_files()
        hub.on_state_change(self._state_changed)
        hub.on_event(self._event)

    # --- storage

    def _load(self) -> None:
        for row in self.store.db.execute("SELECT * FROM flows").fetchall():
            flow = dict(row)
            flow["graph"] = json.loads(flow["graph"])
            flow["enabled"] = bool(flow["enabled"])
            if (self._migrate_state_triggers(flow["graph"]) | self._migrate_state_checks(flow["graph"])
                    | self._migrate_device_inputs(flow["graph"]) | self._migrate_state_outputs(flow["graph"])
                    | self._migrate_event_outputs(flow["graph"])):
                self._save(flow)
            self.flows[flow["id"]] = flow
        for row in self.store.db.execute("SELECT * FROM flow_timers").fetchall():
            self.timers[(row["flow_id"], row["name"])] = {"deadline": row["deadline"], "msg": json.loads(row["msg"])}

    @staticmethod
    def _migrate_state_triggers(graph: dict) -> bool:
        """State triggers used to have one output and a `to` setting; they now have an "on" and an "off"
        output. Move the old connections over so existing flows behave the same."""
        edges, changed = graph.get("edges", []), False
        for node in graph.get("nodes", []):
            d = node.get("data", {})
            if node.get("type") != "trigger.state" or "to" not in d:
                continue
            to = d.pop("to")
            changed = True
            for e in [e for e in edges if e.get("source") == node["id"] and (e.get("sourceHandle") or "out") == "out"]:
                for handle in ({"on": ["on"], "off": ["off"]}.get(to, ["on", "off"])):
                    edges.append({"id": f"{node['id']}-{handle}-{e['target']}", "source": node["id"],
                                  "sourceHandle": handle, "target": e["target"]})
                if to in ("on", "off"):
                    edges.remove(e)
        return changed

    @staticmethod
    def _migrate_state_checks(graph: dict) -> bool:
        """State checks for on/off used a dropdown and "yes" / "no" outputs; they now have "on" and "off"
        outputs. Numeric checks (>, <, =) keep yes / no."""
        changed = False
        for node in graph.get("nodes", []):
            d = node.get("data", {})
            if node.get("type") != "cond.state" or d.get("op") not in ("on", "off"):
                continue
            wants_on = d.pop("op") == "on"
            changed = True
            for e in graph.get("edges", []):
                if e.get("source") == node["id"] and e.get("sourceHandle") in ("yes", "no"):
                    yes = e["sourceHandle"] == "yes"
                    e["sourceHandle"] = "on" if yes == wants_on else "off"
                    e["id"] = f"{node['id']}-{e['sourceHandle']}-{e['target']}"
        return changed

    @staticmethod
    def _migrate_device_inputs(graph: dict) -> bool:
        """Control device used to do one thing, picked from a dropdown ("command"); it now has an input per
        action. Turn the old setting into a single input and connect the existing lines to it."""
        changed = False
        for node in graph.get("nodes", []):
            d = node.get("data", {})
            if node.get("type") != "action.device" or d.get("inputs"):
                continue
            command = d.pop("command", None) or "toggle"
            d["inputs"] = [command]
            for e in graph.get("edges", []):
                if e.get("target") == node["id"]:
                    e["targetHandle"] = command
                    e["id"] = f"{e['source']}-{e.get('sourceHandle') or 'out'}-{node['id']}-{command}"
            changed = True
        return changed

    @staticmethod
    def _migrate_state_outputs(graph: dict) -> bool:
        """Device changes used to watch one entity, picked from a dropdown ("key"), with "on" / "off" / "out"
        outputs; it now has a tick box per change of any of the device's entities, e.g. "occupancy:on"."""
        changed = False
        for node in graph.get("nodes", []):
            d = node.get("data", {})
            if node.get("type") != "trigger.state" or "outputs" in d:
                continue
            key = d.pop("key", None) or ""
            used = []
            for e in graph.get("edges", []):
                if e.get("source") == node["id"]:
                    e["sourceHandle"] = f"{key}:{e.get('sourceHandle') or 'out'}"
                    e["id"] = f"{node['id']}-{e['sourceHandle']}-{e['target']}" + (
                        f"-{e['targetHandle']}" if e.get("targetHandle") else "")
                    used.append(e["sourceHandle"])
            # Not connected yet: offer every kind; the editor only shows the ones the entity can do.
            d["outputs"] = [h for h in (f"{key}:on", f"{key}:off", f"{key}:out") if h in used or not used]
            changed = True
        return changed

    @staticmethod
    def _migrate_event_outputs(graph: dict) -> bool:
        """Button pressed used to have one output, buttons ticked in "keys" and a press type from a dropdown;
        it now has an output per ticked button press ("action:single"). Several of these nodes on the same
        device in one flow (one per press type) become one node with all their outputs."""
        nodes, edges, changed = graph.get("nodes", []), graph.get("edges", []), False
        for node in nodes:
            d = node.get("data", {})
            if node.get("type") != "trigger.event" or "outputs" in d:
                continue
            keys = d.pop("keys", None) or ([d["key"]] if d.get("key") else [])
            d.pop("key", None)
            press = d.pop("action", "") or "*"
            d["outputs"] = [f"{k}:{press}" for k in keys]
            for e in [e for e in edges if e.get("source") == node["id"]]:
                edges.remove(e)
                for out in d["outputs"]:
                    edges.append({**e, "sourceHandle": out, "id": f"{node['id']}-{out}-{e['target']}" + (
                        f"-{e['targetHandle']}" if e.get("targetHandle") else "")})
            changed = True
        if changed:
            first: dict[str, dict] = {}
            for node in list(nodes):
                d = node.get("data", {})
                if node.get("type") != "trigger.event" or not d.get("device_id"):
                    continue
                keep = first.setdefault(d["device_id"], node)
                if keep is node:
                    continue
                keep["data"]["outputs"] += [o for o in d["outputs"] if o not in keep["data"]["outputs"]]
                nodes.remove(node)
                for e in edges:
                    if e.get("source") == node["id"]:
                        e["source"] = keep["id"]
                        e["id"] = f"{keep['id']}-{e['sourceHandle']}-{e['target']}" + (
                            f"-{e['targetHandle']}" if e.get("targetHandle") else "")
            # Merged nodes may now have the same connection twice.
            seen, unique = set(), []
            for e in edges:
                ident = (e.get("source"), e.get("sourceHandle"), e.get("target"), e.get("targetHandle"))
                if ident not in seen:
                    seen.add(ident)
                    unique.append(e)
            edges[:] = unique
        return changed

    def _save(self, flow: dict) -> None:
        self.store.db.execute(
            "INSERT OR REPLACE INTO flows (id, name, enabled, graph, last_run, last_error, updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (flow["id"], flow["name"], int(flow["enabled"]), json.dumps(flow["graph"]),
             flow.get("last_run"), flow.get("last_error"), flow.get("updated", time.time())))
        self.store.db.commit()
        self._write_file(flow)
        self.hub.broadcast({"type": "flows", "flows": self.summary()})  # the automations list updates live

    # --- YAML files

    def _write_file(self, flow: dict) -> None:
        if not self._files_ready or self.files.in_sync(flow):
            return
        try:
            self.files.write(flow)
        except (OSError, ValueError) as err:
            log.error("could not write the file of flow %s: %s", flow["id"], err)
            self.add_log(flow["id"], f"Could not write its file: {err}")

    def _note_issues(self, path, flow: dict | None, errors: list[str], warnings: list[str]) -> None:
        if errors or warnings:
            self.file_issues[path.name] = {"errors": errors, "warnings": warnings}
        else:
            self.file_issues.pop(path.name, None)
        known = flow["id"] if flow else self.files.id_for(path)
        for line in errors:
            log.warning("flow file %s: %s", path.name, line)
            if known in self.flows:
                self.add_log(known, f"{path.name}: {line} (the previous version keeps running)")
        for line in warnings:
            log.info("flow file %s: %s", path.name, line)

    def _apply_file(self, file_flow: dict, path, startup: bool) -> None:
        """Take over what a file says. A flow the app did not know yet is always switched off, so a file that
        someone (or an AI) put there never starts doing things before a person has looked at it."""
        self.files.attach(file_flow, path)  # from here on the file counts as holding exactly this
        flow_id = file_flow["id"]
        old = self.flows.get(flow_id)
        if old is None:
            flow = {**file_flow, "enabled": False, "last_run": None, "last_error": None, "updated": time.time()}
            self.flows[flow_id] = flow
            if file_flow["enabled"]:
                self.add_log(flow_id, "Loaded from its file, switched off until you switch it on here")
                log.info("flow %s is new: loaded switched off", flow_id)
            self._save(flow)
            return
        if flowfiles.content_key(old) == flowfiles.content_key(file_flow):
            return
        if startup:  # nothing is running yet
            old.update(name=file_flow["name"], enabled=file_flow["enabled"], graph=file_flow["graph"], updated=time.time())
            self._save(old)
        else:
            self.update(flow_id, file_flow["name"], file_flow["graph"],
                        file_flow["enabled"] if file_flow["enabled"] != old["enabled"] else None)
            self.add_log(flow_id, f"Reloaded from {path.name}")

    def _load_files(self) -> None:
        self._files_ready = True
        seen: set[str] = set()
        for path, flow, errors, warnings in self.files.read_all():
            if flow and flow["id"] in seen:
                flow, errors = None, [*errors, f"id '{flow['id']}' is already used by another file"]
            self._note_issues(path, flow, errors, warnings)
            if flow:
                seen.add(flow["id"])
                self._apply_file(flow, path, startup=True)
        for flow in list(self.flows.values()):  # flows without a file yet (first start with files, or a deleted file)
            if flow["id"] not in seen and not (self.files.dir / f"{flow['id']}.yaml").exists():
                self._write_file(flow)

    def _watch_files(self) -> None:
        """Pick up files that were added, edited or removed by hand."""
        changed, gone = self.files.scan()
        gone_now = {p.name for p in gone}
        for path in gone:
            if path.name not in self._gone:  # editors save by replacing the file: wait for one more look
                continue
            self._gone.discard(path.name)
            self.files.stamps.pop(path.name, None)
            self.file_issues.pop(path.name, None)
            if (flow_id := self.files.id_for(path)) and flow_id in self.flows:
                log.info("flow file %s was removed: deleting flow %s", path.name, flow_id)
                self.delete(flow_id)
        self._gone = gone_now
        for path in changed:
            flow, errors, warnings = self.files.read(path)
            if flow and (other := self.files.paths.get(flow["id"])) and other != path and other.exists():
                flow, errors = None, [*errors, f"id '{flow['id']}' is already used by {other.name}"]
            self._note_issues(path, flow, errors, warnings)
            if flow:
                self._apply_file(flow, path, startup=False)

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(2)
            try:
                self._watch_files()
            except Exception:
                log.exception("checking the flow files failed")

    def create(self, name: str, graph: dict | None = None, enabled: bool = False, flow_id: str | None = None) -> dict:
        graph = graph or {"nodes": [], "edges": []}
        self._migrate_device_inputs(graph)
        self._migrate_state_outputs(graph)
        self._migrate_event_outputs(graph)
        flow = {"id": flow_id or uuid.uuid4().hex[:12], "name": name, "enabled": enabled,
                "graph": graph, "last_run": None, "last_error": None,
                "updated": time.time()}
        self.flows[flow["id"]] = flow
        self._save(flow)
        return flow

    def update(self, flow_id: str, name: str | None = None, graph: dict | None = None,
               enabled: bool | None = None) -> dict:
        flow = self.flows[flow_id]
        if name is not None:
            flow["name"] = name
        if graph is not None:
            self._migrate_device_inputs(graph)  # an editor tab opened before an upgrade still sends old nodes
            self._migrate_state_outputs(graph)
            self._migrate_event_outputs(graph)
            flow["graph"] = graph
            for ident in [k for k in self._zone if k[0] == flow_id]:
                del self._zone[ident]  # the target may have changed: decide again from the current reading
            for ident in [k for k in self._next_interval if k[0] == flow_id]:
                del self._next_interval[ident]
        if enabled is not None:
            flow["enabled"] = enabled
            self.add_log(flow_id, "Switched on" if enabled else "Switched off")
        flow["updated"] = time.time()
        self._save(flow)
        if graph is not None or enabled:
            self._check_thermostats(flow_id)
        return flow

    def merge(self, flow_id: str, name: str, part_ids: list[str]) -> dict:
        """Combine flows into one, parts under each other; running timers move along. On when any part was on."""
        parts = [self.flows[p] for p in part_ids if p in self.flows]
        graph, renames = stack_graphs([p["graph"] for p in parts])
        flow = self.create(name, graph, enabled=any(p["enabled"] for p in parts), flow_id=flow_id)
        for part, rename in zip(parts, renames):
            for (fid, node_id) in [k for k in self.timers if k[0] == part["id"]]:
                new = rename.get(node_id, node_id)
                self.timers[(flow_id, new)] = self.timers.pop((fid, node_id))
                self.store.db.execute("UPDATE flow_timers SET flow_id = ?, name = ?, node_id = ? "
                                      "WHERE flow_id = ? AND name = ?", (flow_id, new, new, fid, node_id))
            self.delete(part["id"])
        self.store.db.commit()
        self.add_log(flow_id, f"Combined from: {', '.join(p['name'] for p in parts)}")
        return flow

    def delete(self, flow_id: str) -> None:
        for node_id in [k[1] for k in self.timers if k[0] == flow_id]:
            self._stop_timer(flow_id, node_id)
        self.flows.pop(flow_id, None)
        self.logs.pop(flow_id, None)
        self.store.db.execute("DELETE FROM flows WHERE id = ?", (flow_id,))
        self.store.db.commit()
        self.files.remove(flow_id)
        self.hub.broadcast({"type": "flows", "flows": self.summary()})

    def add_log(self, flow_id: str, message: str) -> None:
        line = {"time": time.time(), "message": message}
        self.logs.setdefault(flow_id, deque(maxlen=200)).append(line)
        self.hub.broadcast({"type": "log", "flow_id": flow_id, "line": line})
        log.info("[flow %s] %s", self.flows.get(flow_id, {}).get("name", flow_id), message)

    # --- triggers

    def start(self) -> None:
        self._task = asyncio.create_task(self._clock())
        self._watcher = asyncio.create_task(self._watch())

    def stop(self) -> None:
        for task in (self._task, self._watcher):
            if task:
                task.cancel()

    def _triggers(self, kind: str):
        for flow in list(self.flows.values()):
            if not flow["enabled"]:
                continue
            for node in flow["graph"].get("nodes", []):
                if node.get("type") == kind:
                    yield flow, node

    def _state_changed(self, device: Device, entity: Entity, old: Any, new: Any) -> None:
        for flow, node in self._triggers("trigger.state"):
            d = node.get("data", {})
            # On/off entities follow their "<entity>:on" or ":off" output; numeric ones have a single ":out".
            handle = f"{entity.key}:" + (("on" if new else "off") if isinstance(new, bool) else "out")
            if d.get("device_id") != device.id or handle not in (d.get("outputs") or []):
                continue
            self._fire(flow, node, {"trigger": "state", "device_id": device.id, "key": entity.key,
                                    "old": old, "new": new}, handle)
        for flow, node in self._triggers("trigger.thermostat"):
            d = node.get("data", {})
            if d.get("device_id") == device.id and d.get("key") == entity.key:
                self._thermostat(flow, node, new)

    def _thermostat(self, flow: dict, node: dict, reading: Any) -> None:
        d = node.get("data", {})
        try:
            temp, target, margin = float(reading), float(d.get("target", 20)), float(d.get("margin", 0.5))
        except (TypeError, ValueError):
            return
        # Between the two limits nothing happens, so a heater does not flick on and off.
        zone = "cold" if temp <= target - margin else "warm" if temp >= target + margin else None
        ident = (flow["id"], node["id"])
        if zone and self._zone.get(ident) != zone:
            self._zone[ident] = zone
            self.hub.broadcast({"type": "flow", "flow_id": flow["id"], "zones": {node["id"]: zone}})
            self._fire(flow, node, {"trigger": "thermostat", "device_id": d.get("device_id"), "key": d.get("key"),
                                    "temperature": temp}, zone)

    def _check_thermostats(self, flow_id: str | None = None) -> None:
        """Act on the current reading right away (at startup, or when a flow is saved or switched on)
        instead of waiting until the temperature changes."""
        for flow, node in self._triggers("trigger.thermostat"):
            if flow_id in (None, flow["id"]):
                _, entity = self._entity(node.get("data", {}))
                if entity:
                    self._thermostat(flow, node, entity.state)

    def _event(self, device: Device, key: str, action: str, data: dict) -> None:
        for flow, node in self._triggers("trigger.event"):
            d = node.get("data", {})
            outs = d.get("outputs") or []
            handle = next((h for h in (f"{key}:{action}", f"{key}:*") if h in outs), None)
            if d.get("device_id") != device.id or handle is None:
                continue
            self._fire(flow, node, {"trigger": "event", "device_id": device.id, "key": key,
                                    "action": action, "count": data.get("count", 1)}, handle)

    async def _clock(self) -> None:
        await asyncio.sleep(15)  # let adapters load devices first
        self._check_thermostats()
        while True:
            now = time.time()
            hhmm, today = datetime.now().strftime("%H:%M"), datetime.now().strftime("%Y-%m-%d")
            for flow, node in self._triggers("trigger.time"):
                ident = (flow["id"], node["id"])
                days = node.get("data", {}).get("days")
                if (node.get("data", {}).get("at") == hhmm and self._fired_today.get(ident) != today
                        and (not days or datetime.now().weekday() in days)):
                    self._fired_today[ident] = today
                    self._fire(flow, node, {"trigger": "time", "at": hhmm})
            for flow, node in self._triggers("trigger.sun"):
                ident = (flow["id"], node["id"])
                t = sun.times()
                if not t or self._fired_today.get(ident) == today:
                    continue
                d = node.get("data", {})
                due = t[0 if d.get("event") == "sunrise" else 1] + timedelta(minutes=float(d.get("offset") or 0))
                if 0 <= (datetime.now().astimezone() - due).total_seconds() < 120:  # not for a time long past (restart)
                    self._fired_today[ident] = today
                    self._fire(flow, node, {"trigger": "sun", "event": d.get("event")})
            for flow, node in self._triggers("trigger.interval"):
                ident = (flow["id"], node["id"])
                seconds = max(5, float(node.get("data", {}).get("seconds") or 60))
                if now >= self._next_interval.setdefault(ident, now):
                    self._next_interval[ident] = now + seconds
                    self._fire(flow, node, {"trigger": "interval"})
            for (flow_id, node_id), t in list(self.timers.items()):
                if now >= t["deadline"]:
                    self._stop_timer(flow_id, node_id)
                    flow = self.flows.get(flow_id)
                    node = next((n for n in flow["graph"].get("nodes", []) if n["id"] == node_id), None)                         if flow and flow["enabled"] else None
                    if node:
                        self.add_log(flow_id, "Timer ran out")
                        self._fire(flow, node, t["msg"])
            await asyncio.sleep(1)

    def _start_timer(self, flow_id: str, node: dict, msg: dict) -> None:
        d = node.get("data", {})
        if (flow_id, node["id"]) in self.timers and d.get("restart") is False:
            return  # keep the countdown that is already running
        t = {"deadline": time.time() + float(d.get("minutes") or 0) * 60, "msg": msg}
        self.timers[(flow_id, node["id"])] = t
        self.store.db.execute("INSERT OR REPLACE INTO flow_timers VALUES (?, ?, ?, ?, ?)",
                              (flow_id, node["id"], node["id"], t["deadline"], json.dumps(msg, default=str)))
        self.store.db.commit()
        self.hub.broadcast({"type": "flow", "flow_id": flow_id, "waiting": {node["id"]: t["deadline"] - time.time()}})

    def _stop_timer(self, flow_id: str, node_id: str) -> bool:
        if not self.timers.pop((flow_id, node_id), None):
            return False
        self.store.db.execute("DELETE FROM flow_timers WHERE flow_id = ? AND name = ?", (flow_id, node_id))
        self.store.db.commit()
        self.hub.broadcast({"type": "flow", "flow_id": flow_id, "waiting": {node_id: None}})
        return True

    def _fire(self, flow: dict, node: dict, msg: dict, handle: str = "out") -> None:
        if config.AUTOMATIONS:
            self.hub.spawn(self._run(flow, node, msg, handle))

    def webhook(self, name: str) -> int:
        """Fire every enabled trigger.webhook with this name; returns how many fired."""
        fired = 0
        for flow, node in self._triggers("trigger.webhook"):
            if node.get("data", {}).get("name") == name:
                self._fire(flow, node, {"trigger": "webhook", "name": name})
                fired += 1
        return fired

    async def run_now(self, flow_id: str, node_id: str) -> None:
        flow = self.flows[flow_id]
        node = next(n for n in flow["graph"]["nodes"] if n["id"] == node_id)
        handle = {"trigger.state": (node.get("data", {}).get("outputs") or ["out"])[0],
                  "trigger.event": (node.get("data", {}).get("outputs") or ["out"])[0],
                  "trigger.thermostat": "cold"}.get(node.get("type"), "out")
        await self._run(flow, node, {"trigger": "manual"}, handle)

    # --- execution

    async def _run(self, flow: dict, start: dict, msg: dict, handle: str = "out") -> None:
        flow["last_run"] = time.time()
        steps = [0]
        try:
            await self._follow(flow, start, msg, handle, steps)
            flow["last_error"] = None
        except Exception as err:
            log.exception("flow %s failed", flow["name"])
            flow["last_error"] = f"{type(err).__name__}: {err}"
            self.add_log(flow["id"], f"Error: {err}")
        self._save(flow)

    async def _follow(self, flow: dict, node: dict, msg: dict, handle: str, steps: list[int]) -> None:
        nodes = {n["id"]: n for n in flow["graph"].get("nodes", [])}
        taken = [e for e in flow["graph"].get("edges", [])
                 if e.get("source") == node["id"] and (e.get("sourceHandle") or "out") == handle
                 and e.get("target") in nodes]
        if taken:
            ids = [e.get("id") or f"{e['source']}-{handle}-{e['target']}" for e in taken]
            self.passed.setdefault(flow["id"], {}).update(dict.fromkeys(ids, time.time()))
            self.hub.broadcast({"type": "flow", "flow_id": flow["id"], "passed": ids})
        nexts = [(nodes[e["target"]], e.get("targetHandle") or "in") for e in taken]
        await asyncio.gather(*(self._step(flow, n, dict(msg), steps, inp) for n, inp in nexts))

    async def _step(self, flow: dict, node: dict, msg: dict, steps: list[int], inp: str = "in") -> None:
        steps[0] += 1
        if steps[0] > MAX_STEPS:
            raise RuntimeError("flow ran more than 200 steps; is there a loop?")
        kind, d = node.get("type", ""), node.get("data", {})
        if kind in plugins.node_types():  # a node an integration adds
            await plugins.node_types()[kind][1].run(NodeRun(self, flow, node, msg, steps))
            return
        if kind == "trigger.thermostat":
            # Fed by another step: judge the current temperature now, whatever side it was on before.
            _, entity = self._entity(d)
            try:
                temp, target, margin = float(entity.state), float(d.get("target", 20)), float(d.get("margin", 0.5))
            except (AttributeError, TypeError, ValueError):
                return
            zone = "cold" if temp <= target - margin else "warm" if temp >= target + margin else None
            if zone:
                self._zone[(flow["id"], node["id"])] = zone
                self.hub.broadcast({"type": "flow", "flow_id": flow["id"], "zones": {node["id"]: zone}})
                await self._follow(flow, node, {**msg, "temperature": temp}, zone, steps)
        elif kind == "cond.state" and d.get("op") in (None, ""):
            _, entity = self._entity(d)
            await self._follow(flow, node, msg, "on" if entity and entity.state is True else "off", steps)
        elif kind.startswith("cond."):
            handle = "yes" if self._check(kind, d) else "no"
            await self._follow(flow, node, msg, handle, steps)
        elif kind == "action.delay":
            await asyncio.sleep(max(0.0, float(d.get("seconds") or 0)))
            await self._follow(flow, node, msg, "out", steps)
        elif kind == "action.timer":
            if inp == "stop":
                if self._stop_timer(flow["id"], node["id"]):
                    self.add_log(flow["id"], "Timer stopped")
            else:
                self._start_timer(flow["id"], node, msg)  # the clock continues from this node when it runs out
        elif kind == "action.log":
            self.add_log(flow["id"], _fill(d.get("message"), msg))
            await self._follow(flow, node, msg, "out", steps)
        elif kind == "action.var":
            name, value = str(d.get("name") or ""), _fill(d.get("value"), msg)
            self.store.set_var(name, value)
            self.hub.broadcast({"type": "variables", "variables": self.store.variables()})
            self.add_log(flow["id"], f"{name} = {value}")
            await self._follow(flow, node, msg, "out", steps)
        elif kind == "action.throttle":
            key, now = (flow["id"], node["id"]), time.time()
            if now - self._throttled.get(key, 0) >= float(d.get("minutes") or 0) * 60:
                self._throttled[key] = now
                await self._follow(flow, node, msg, "out", steps)
        elif kind == "action.http":
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.request(str(d.get("method") or "GET"), _fill(d.get("url"), msg),
                                             content=_fill(d.get("body"), msg) or None)
                self.add_log(flow["id"], f"{d.get('method') or 'GET'} {d.get('url')} → {r.status_code}")
            except Exception as err:  # a website being down should not stop the rest of the flow
                self.add_log(flow["id"], f"Request failed: {err}")
            await self._follow(flow, node, msg, "out", steps)
        elif kind == "action.flow":
            other = self.flows.get(str(d.get("flow_id")))
            if not other:
                raise LookupError("flow not found")
            for trigger in [n for n in other["graph"].get("nodes", []) if n.get("type") == "trigger.manual"]:
                await self._follow(other, trigger, dict(msg), "out", steps)
            self.add_log(flow["id"], f"Ran flow: {other['name']}")
            await self._follow(flow, node, msg, "out", steps)
        elif kind == "action.cycle":
            payload = self._cycle(flow, node, inp)
            self.add_log(flow["id"], f"Cycle: {json.dumps(payload)}")
            await self._follow(flow, node, {**msg, "payload": payload}, "out", steps)
        elif kind == "action.repeat":
            key = (flow["id"], node["id"])
            if inp == "stop":
                task = self._repeats.pop(key, None)
                if task:
                    task.cancel()
                    self.add_log(flow["id"], "Repeat stopped")
            elif key not in self._repeats:
                self._repeats[key] = asyncio.create_task(self._repeat(flow, node, msg))
        elif kind == "action.device":
            # The input the message came in on is the action; old single-input nodes still have "command".
            command = inp if inp != "in" else d.get("command") or (d.get("inputs") or ["toggle"])[0]
            if command in ("loop_start", "loop_stop"):
                self._brightness_loop(flow, node, command)
            else:
                await self._device_action(flow, d, msg, command)
            await self._follow(flow, node, msg, "out", steps)

    def _entity(self, d: dict) -> tuple[Device, Entity] | tuple[None, None]:
        device = self.hub.devices.get(d.get("device_id", ""))
        entity = device.entities.get(d.get("key", "")) if device else None
        return (device, entity) if entity else (None, None)

    def _check(self, kind: str, d: dict) -> bool:
        if kind == "cond.var":
            same = (self.store.get_var(str(d.get("name") or "")) or "") == str(d.get("value") or "")
            return same if d.get("op", "eq") == "eq" else not same
        if kind == "cond.day":
            return datetime.now().weekday() in (d.get("days") or [])
        if kind == "cond.dark":
            return sun.is_dark()
        if kind == "cond.time":
            now = datetime.now().strftime("%H:%M")
            start, end = d.get("from", "00:00"), d.get("to", "23:59")
            return start <= now < end if start <= end else (now >= start or now < end)
        device, entity = self._entity(d)
        if not entity:
            return False
        if kind == "cond.for":
            minutes = float(d.get("minutes") or 0) * 60
            state = d.get("state", "on")
            if state in ("above", "below"):
                # Numeric: track since when the value has been past the limit (per node, in memory).
                try:
                    past = float(entity.state) > float(d.get("value")) if state == "above" \
                        else float(entity.state) < float(d.get("value"))
                except (TypeError, ValueError):
                    past = False
                ident = (device.id, entity.key, state, str(d.get("value")))
                if not past:
                    self._past_since.pop(ident, None)
                    return False
                return time.time() - self._past_since.setdefault(ident, time.time()) >= minutes
            since = self.hub.since(device.id, entity.key)
            return entity.state is (state == "on") and since is not None and time.time() - since >= minutes
        op, value = d.get("op", "on"), d.get("value")
        if op == "on":
            return entity.state is True
        if op == "off":
            return entity.state is False
        try:
            if op == "gt":
                return float(entity.state) > float(value)
            if op == "lt":
                return float(entity.state) < float(value)
        except (TypeError, ValueError):
            return False
        return str(entity.state) == str(value)

    async def _device_action(self, flow: dict, d: dict, msg: dict, command: str) -> None:
        device, entity = self._entity(d)
        if not entity:
            raise LookupError(f"device {d.get('device_id')}/{d.get('key')} not found")
        if command in ("brightness", "brighter", "dimmer") and entity.kind != "light":
            raise ValueError(f"{device.name} can only switch on and off, not dim")
        if command in ("brighter", "dimmer"):
            step = float(d.get("step") or 5) * int(msg.get("count") or 1)
            current = entity.brightness if entity.state else 0
            if command == "dimmer" and not entity.state:
                return  # dimming a light that is off does nothing
            target = (current or 0) + step if command == "brighter" else (current or 0) - step
            target = int(max(int(d.get("min") or 1), min(100, round(target))))
            await self.hub.command(device.id, entity.key, brightness=target)
            self.add_log(flow["id"], f"{device.name}: {target}%")
        elif command == "message":
            payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
            if "brightness" in payload:
                level = int(payload["brightness"])
                if entity.kind != "light":
                    raise ValueError(f"{device.name} can only switch on and off, not dim")
                await self.hub.command(device.id, entity.key, **({"brightness": level} if level > 0 else {"on": False}))
            elif payload.get("toggle"):
                await self.hub.command(device.id, entity.key, toggle=True)
            elif "on" in payload:
                await self.hub.command(device.id, entity.key, on=bool(payload["on"]))
            else:
                raise ValueError("message has nothing for a device (brightness, on or toggle)")
            self.add_log(flow["id"], f"{device.name}: {json.dumps(payload)}")
        elif command == "brightness":
            await self.hub.command(device.id, entity.key, brightness=int(d.get("brightness") or 100))
            self.add_log(flow["id"], f"{device.name}: {d.get('brightness')}%")
        else:
            kwargs = {"toggle": True} if command == "toggle" else {"on": command == "on"}
            await self.hub.command(device.id, entity.key, **kwargs)
            self.add_log(flow["id"], f"{device.name}: {command}")

    def _brightness_loop(self, flow: dict, node: dict, command: str) -> None:
        key = (flow["id"], node["id"])
        if command == "loop_stop":
            if task := self._loops.pop(key, None):
                task.cancel()
                self.add_log(flow["id"], "Brightness loop stopped")
            return
        device, entity = self._entity(node.get("data", {}))
        if not entity:
            raise LookupError("device for the brightness loop not found")
        if entity.kind != "light":
            raise ValueError(f"{device.name} can only switch on and off, not dim")
        if key not in self._loops:  # already running: leave it be
            self._loops[key] = asyncio.create_task(self._loop(flow, node, device, entity))

    async def _loop(self, flow: dict, node: dict, device: Device, entity: Entity) -> None:
        """Step a light through brightness levels, over and over, until stopped or the time limit is up."""
        d, key = node.get("data", {}), (flow["id"], node["id"])
        levels = [max(0, min(100, int(v))) for v in d.get("loop_levels") or [25, 50, 75, 100]] or [100]
        every, until = max(0.2, float(d.get("loop_seconds") or 1)), time.time() + max(1.0, float(d.get("loop_max_seconds") or 60))
        self.add_log(flow["id"], f"{device.name}: brightness loop {' → '.join(map(str, levels))}% every {every:g}s")
        try:
            step = 0
            while time.time() < until:
                level = levels[step % len(levels)]
                await self.hub.command(device.id, entity.key, **({"brightness": level} if level > 0 else {"on": False}))
                step += 1
                await asyncio.sleep(every)
            self.add_log(flow["id"], f"{device.name}: brightness loop ended (time limit)")
        except asyncio.CancelledError:
            raise
        except Exception as err:
            log.exception("flow %s brightness loop failed", flow["name"])
            self.add_log(flow["id"], f"Error: {err}")
        finally:
            if self._loops.get(key) is asyncio.current_task():
                del self._loops[key]

    async def _repeat(self, flow: dict, node: dict, msg: dict) -> None:
        """Send the message on every N seconds until a stop arrives (or the safety limit runs out)."""
        d, key = node.get("data", {}), (flow["id"], node["id"])
        every, until = max(0.1, float(d.get("seconds") or 1)), time.time() + float(d.get("max_seconds") or 60)
        self.add_log(flow["id"], f"Repeat every {every:g}s")
        try:
            while time.time() < until:
                await self._follow(flow, node, dict(msg), "out", [0])
                await asyncio.sleep(every)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            log.exception("flow %s repeat failed", flow["name"])
            self.add_log(flow["id"], f"Error: {err}")
        finally:
            if self._repeats.get(key) is asyncio.current_task():
                del self._repeats[key]

    def _cycle(self, flow: dict, node: dict, inp: str) -> dict:
        """The next message of a Cycle node; the position is remembered across restarts."""
        d = node.get("data", {})
        steps = [s if isinstance(s, dict) else {"brightness": s} for s in d.get("steps") or []]
        if not steps:
            raise LookupError("cycle has no steps")
        setting = f"cycle:{flow['id']}:{node['id']}"
        saved = self.store.get(setting)
        at = int(saved) if saved is not None else None  # None: nothing sent yet
        last = len(steps) - 1
        if inp == "back":
            to = 0 if at is None else max(0, at - 1)
        elif inp == "loop":
            to = 0 if at is None or at >= last else at + 1
        else:
            to = 0 if at is None else min(last, at + 1)
        self.store.set(setting, str(to))
        return steps[to]

    def activity(self, flow_id: str) -> dict:
        """What the editor colours when it opens: connections used in the last few seconds, timers counting
        down (seconds left) and the side each thermostat is on. After that, changes arrive over the WebSocket as {"type": "flow", ...}."""
        now = time.time()
        return {"passed": [e for e, t in self.passed.get(flow_id, {}).items() if now - t < 4],
                "waiting": {node_id: t["deadline"] - now for (f, node_id), t in self.timers.items() if f == flow_id},
                "zones": {node_id: zone for (f, node_id), zone in self._zone.items() if f == flow_id}}

    async def run_flow(self, flow_id: str) -> int:
        """The Run button: start every manual trigger of a flow, whether or not the flow is switched on."""
        flow = self.flows[flow_id]
        nodes = [n for n in flow["graph"].get("nodes", []) if n.get("type") == "trigger.manual"]
        for n in nodes:
            await self._run(flow, n, {"trigger": "manual"})
        return len(nodes)

    def summary(self) -> list[dict]:
        return [{k: f[k] for k in ("id", "name", "enabled", "last_run", "last_error", "updated")}
                | {"nodes": len(f["graph"].get("nodes", [])),
                   "manual": any(n.get("type") == "trigger.manual" for n in f["graph"].get("nodes", []))} for f in self.flows.values()]
