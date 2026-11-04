"""Changes to flows made at start-up for installs from before a feature existed."""

from __future__ import annotations

from .adapters.hue import legacy_buttons
from .flows import FlowEngine


def adopt_hue_buttons(engine: FlowEngine) -> None:
    """Hue presses used to arrive in flows as "Notification button" triggers named after the switch button.
    Turn those into "Button pressed" on the Hue switch, keeping the node and its connections."""
    hue_buttons = legacy_buttons()
    if not hue_buttons:
        return
    for flow in engine.flows.values():
        changed = False
        for node in flow["graph"].get("nodes", []):
            name = node.get("data", {}).get("name")
            if node.get("type") == "trigger.webhook" and name in hue_buttons:
                device_id, key = hue_buttons[name]
                node["type"], node["data"] = "trigger.event", {"device_id": device_id, "outputs": [f"{key}:press"]}
                for e in flow["graph"].get("edges", []):
                    if e.get("source") == node["id"]:
                        e["sourceHandle"] = f"{key}:press"
                changed = True
        if changed:
            engine._save(flow)
            engine.add_log(flow["id"], "Hue buttons now use the Hue switch device")
