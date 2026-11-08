"""Changes to flows made at start-up for installs from before a feature existed."""

from __future__ import annotations

from . import config
from .plugins.hue.adapter import legacy_buttons
from .flows import FlowEngine

THERMOSTAT_KEYS = ["thermostat_id", "thermostat_name", "thermostat_sensor_device", "thermostat_sensor_key",
                   "thermostat_heater_device", "thermostat_heater_key"]


def retire_thermostat(engine: FlowEngine) -> None:
    """The thermostat used to be an integration with a device of its own (a room sensor and a heater plug).
    It is now only the Thermostat node in a flow. Turn the old settings into such a flow, switched off like any
    flow that arrives from outside, and drop the integration. Safe to run again: it only acts while the old
    settings are there, and never replaces a flow that exists."""
    sensor = (config.THERMOSTAT_SENSOR_DEVICE, config.THERMOSTAT_SENSOR_KEY)
    heater = (config.THERMOSTAT_HEATER_DEVICE, config.THERMOSTAT_HEATER_KEY)
    if all((*sensor, *heater)) and "thermostat" not in engine.flows:
        try:
            target = float(engine.store.get("thermostat_target") or 18.0)
        except ValueError:
            target = 18.0
        heat = {"device_id": heater[0], "key": heater[1], "brightness": 50, "step": 5, "min": 1}
        graph = {
            "nodes": [
                {"id": "room", "type": "trigger.thermostat", "position": {"x": 0, "y": 80},
                 "data": {"device_id": sensor[0], "key": sensor[1], "target": target, "margin": 0.5}},
                {"id": "heat-on", "type": "action.device", "position": {"x": 320, "y": 0},
                 "data": {**heat, "inputs": ["on"]}},
                {"id": "heat-off", "type": "action.device", "position": {"x": 320, "y": 160},
                 "data": {**heat, "inputs": ["off"]}},
            ],
            "edges": [
                {"id": "room-cold-heat-on", "source": "room", "sourceHandle": "cold", "target": "heat-on",
                 "targetHandle": "on"},
                {"id": "room-warm-heat-off", "source": "room", "sourceHandle": "warm", "target": "heat-off",
                 "targetHandle": "off"},
            ],
        }
        engine.create(config.THERMOSTAT_NAME or "Heating", graph, enabled=False, flow_id="thermostat")
        engine.add_log("thermostat", "Made from the old thermostat settings. Switched off: check it, then switch it on")
    if "thermostat" in config.INTEGRATIONS:
        config.save({"integrations": ",".join(i for i in config.INTEGRATIONS if i != "thermostat") or "none"})
    if any((*sensor, *heater)):
        config.save({key: "" for key in THERMOSTAT_KEYS})


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
