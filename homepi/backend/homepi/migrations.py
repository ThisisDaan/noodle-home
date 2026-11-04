"""Changes to flows made at start-up for installs from before a feature existed."""

from __future__ import annotations

from .adapters.hue import BUTTONS as HUE_BUTTONS
from .flows import FlowEngine


def adopt_hue_buttons(engine: FlowEngine) -> None:
    """Hue presses used to arrive in flows as "Notification button" triggers named e.g. boven_hue.
    Turn those into "Button pressed" on the Hue switch, keeping the node and its connections."""
    for flow in engine.flows.values():
        changed = False
        for node in flow["graph"].get("nodes", []):
            name = node.get("data", {}).get("name")
            if node.get("type") == "trigger.webhook" and name in HUE_BUTTONS:
                device_id, key = HUE_BUTTONS[name]
                node["type"], node["data"] = "trigger.event", {"device_id": device_id, "outputs": [f"{key}:press"]}
                for e in flow["graph"].get("edges", []):
                    if e.get("source") == node["id"]:
                        e["sourceHandle"] = f"{key}:press"
                changed = True
        if changed:
            engine._save(flow)
            engine.add_log(flow["id"], "Hue buttons now use the Hue switch device")
