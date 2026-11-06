"""Everything an AI (or a person) needs to write a flow for this hub in one place: how the format works, which
nodes exist, the real devices and their entities, the rooms, the flows that already exist and a few examples.
Served by GET /api/flow/context (JSON, or ?format=markdown as a prompt to paste into an AI chat)."""

from __future__ import annotations

from pathlib import Path

from . import flowfiles, flows as flows_module
from .yamlfile import plain

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples" / "flows"

RULES = """\
You write automation flows for the Noodle smart home hub. Answer with ONE YAML document in the file format
described below, in a single code block, and nothing else except short comments inside the YAML.

Rules
- Use only node types from "Nodes", and only device ids and entity keys from "Devices", spelled exactly. If a
  device the request needs is missing, say so in a YAML comment instead of inventing one.
- Give every node a short readable id (change, wait, lamp_off). Edges go from an output of one node to an input
  of the next: {from: a, out: <output>, to: b, in: <input>}. `out` defaults to "out"; leave `in` out unless the
  target node has named inputs (action.timer: start/stop, action.device: the ticked actions).
- Outputs: trigger.state has one output per ticked change, named "<entity key>:on", "<entity key>:off" or
  "<entity key>:out" (numbers); trigger.event one per ticked press "<button key>:<press>"; cond.* nodes have
  "yes"/"no" (on/off entities "on"/"off"); everything else "out".
- A flow can put a card on the dashboard with a top-level `card:` section: {title, controls: [{id, type, label,
  ...}], show: [...]}. Control types: switch, dial and slider (min, max, step, unit, default), button, select
  (options). Show items: {type: value, device_id, key, label}, {type: status, variable, label} (a variable that an
  action.var step writes) and {type: graph, device_id, key}. A control starts a trigger.control node with
  data {control: <id>} (outputs "on"/"off" for a switch, "out" with the value for all); a numeric setting of any
  node (thermostat target and margin, timer minutes) may be "{control.<id>}" to use the control's value; a
  cond.var on the variable "<flow id>.<control id>" checks a switch ("on"/"off"). Use a card when the request
  wants something to look at or adjust on the dashboard; see the heater-card example.
- Always write `enabled: false`. A person switches a flow on after reading it.
- Keep it simple and add a short comment above each step saying what it does. Prefer an action.timer or
  cond.for over polling (use action.timer for any wait, never action.delay: it is lost on a restart), and add a safety net (for example a timer that switches a heater off) when the
  request is about something that can run unattended.
"""


def devices(hub) -> list[dict]:
    """The devices with their entities as a flow can use them."""
    out = []
    for d in hub.devices.values():
        entities = []
        for e in d.entities.values():
            item = {"key": e.key, "kind": e.kind, "name": e.name}
            if e.device_class:
                item["device_class"] = e.device_class
            if e.unit:
                item["unit"] = e.unit
            if e.actions:
                item["presses"] = list(e.actions)
            if e.state is not None and e.kind != "button":
                item["state"] = e.state
            entities.append(item)
        out.append({"id": d.id, "name": d.name, "area": d.area, "source": d.source, "entities": entities})
    return sorted(out, key=lambda d: (d["area"] or "~", d["name"].lower()))


def examples() -> list[dict]:
    found = []
    for path in sorted(EXAMPLES_DIR.glob("*.yaml")):
        found.append({"name": path.stem, "yaml": path.read_text(encoding="utf-8")})
    return found


def nodes() -> list[dict]:
    return [{"type": t, "label": s["label"], "category": s["category"], "help": s["help"],
             "settings": {k: {"type": f[0], "description": f[1], **({"allowed": f[2]} if len(f) > 2 else {})}
                          for k, f in s["fields"].items()}}
            for t, s in sorted(flowfiles.node_specs().items())]


def build(hub, engine, store) -> dict:
    return {
        "instructions": RULES,
        "format": flowfiles.__doc__.strip(),
        "engine_reference": flows_module.__doc__.strip(),
        "schema": flowfiles.schema(),
        "nodes": nodes(),
        "devices": devices(hub),
        "areas": store.areas(),
        "variables": sorted(store.variables()),
        "flows": [{"id": f["id"], "name": f["name"], "enabled": f["enabled"]} for f in engine.flows.values()],
        "examples": examples(),
    }


def markdown(ctx: dict) -> str:
    lines = [ctx["instructions"], "", "## File format", "", ctx["format"], "", "## Nodes", ""]
    for n in ctx["nodes"]:
        lines.append(f"- **{n['type']}** ({n['label']}): {n['help']}")
        for key, f in n["settings"].items():
            allowed = f" One of: {', '.join(f['allowed'])}." if f.get("allowed") else ""
            lines.append(f"  - `{key}` ({f['type']}): {f['description']}{allowed}")
    lines += ["", "## How the engine runs a flow", "", ctx["engine_reference"], "", "## Devices", ""]
    for d in ctx["devices"]:
        lines.append(f"- `{d['id']}` {d['name']}" + (f" ({d['area']})" if d["area"] else ""))
        for e in d["entities"]:
            extra = [e["kind"] + (f"/{e['device_class']}" if e.get("device_class") else "")]
            if "unit" in e:
                extra.append(e["unit"])
            if "presses" in e:
                extra.append("presses: " + ", ".join(e["presses"]))
            if "state" in e:
                extra.append(f"now {e['state']}")
            lines.append(f"  - `{e['key']}` {e['name']} ({'; '.join(extra)})")
    if not ctx["devices"]:
        lines.append("(no devices are connected yet)")
    lines += ["", "Rooms: " + (", ".join(ctx["areas"]) or "none"), "",
              "Existing flows: " + (", ".join(f"{f['id']} ({f['name']})" for f in ctx["flows"]) or "none")]
    lines += ["", "## Examples"]
    for ex in ctx["examples"]:
        lines += ["", f"### {ex['name']}", "", "```yaml", ex["yaml"].rstrip(), "```"]
    lines += ["", "## My request", "", "(describe the automation here)"]
    return "\n".join(lines) + "\n"


def device_warnings(flow: dict, hub) -> list[str]:
    """Problems that depend on this hub: devices or entities a flow names that are not here."""
    warnings = []
    for node in flow["graph"].get("nodes", []):
        data = node.get("data") or {}
        device_id, key = data.get("device_id"), data.get("key")
        if not device_id:
            continue
        device = hub.devices.get(device_id)
        if device is None:
            warnings.append(f"node {node['id']}: no device '{device_id}' on this hub")
        elif key and key not in device.entities:
            warnings.append(f"node {node['id']}: {device.name} has no entity '{key}' "
                            f"(it has: {', '.join(device.entities)})")
    return warnings


def check(text: str, hub) -> dict:
    """Validate the text of a flow file. {ok, errors, warnings, id, name, nodes} (flow facts only when ok)."""
    try:
        doc = flowfiles.parse(text)
    except Exception as err:
        first = str(err).strip().splitlines()[0] if str(err).strip() else "Not valid YAML"
        return {"ok": False, "errors": [first], "warnings": []}
    errors, warnings = flowfiles.validate(doc)
    result: dict = {"ok": not errors, "errors": errors, "warnings": warnings}
    if not errors:
        flow = flowfiles.from_doc(plain(doc))
        result |= {"id": flow["id"], "name": flow["name"], "nodes": len(flow["graph"]["nodes"]),
                   "warnings": [*warnings, *device_warnings(flow, hub)]}
    return result
