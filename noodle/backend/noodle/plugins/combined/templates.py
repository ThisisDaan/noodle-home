"""What can be combined. A template says which devices it needs, shows the result as one device and, when work has
to be done, writes the flow that does it, so a combined device is never magic: its flow can be opened and read.

A template has `inputs`. A "sensor" or "switch" input called `x` is stored as `x_device` and `x_key`; a "number"
input is stored under its own key. To add a template: subclass Template, list it in TEMPLATES, add a test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...hub import Entity, Hub


@dataclass(frozen=True)
class Input:
    key: str
    kind: str  # "sensor", "switch" or "number"
    label: str
    default: Any = None
    device_class: str | None = None  # sensor: only readings of this class (None: any number)
    min: float | None = None  # number: the allowed range
    max: float | None = None


class Template:
    id = ""
    name = ""
    help = ""
    model = ""
    inputs: list[Input] = []
    always_on = False  # no off position: its flow runs whenever the device exists (a timer plug)

    # --- inputs

    def defaults(self) -> dict:
        return {i.key: i.default for i in self.inputs if i.default is not None}

    def clean(self, values: dict) -> dict:
        out = {**self.defaults(), **values}
        for i in self.inputs:
            if i.kind == "number":
                try:
                    out[i.key] = float(out[i.key])
                except (KeyError, TypeError, ValueError):
                    raise ValueError(f"{i.label} must be a number") from None
        keep = {f"{i.key}_device" for i in self.inputs if i.kind != "number"} | {f"{i.key}_key" for i in self.inputs if i.kind != "number"}
        keep |= {i.key for i in self.inputs if i.kind == "number"}
        return {k: v for k, v in out.items() if k in keep}

    def validate(self, values: dict, devices: dict) -> list[str]:
        errors = []
        for i in self.inputs:
            if i.kind == "number":
                if (i.min is not None and values[i.key] < i.min) or (i.max is not None and values[i.key] > i.max):
                    errors.append(f"{i.label} must be between {i.min:g} and {i.max:g}")
                continue
            device, key = values.get(f"{i.key}_device"), values.get(f"{i.key}_key")
            if not device or not key:
                errors.append(f"Choose: {i.label}")
            elif device not in devices or key not in devices[device].entities:
                errors.append(f"{i.label} is not a known device")
            elif i.kind == "switch" and devices[device].entities[key].kind not in ("switch", "light"):
                errors.append(f"{i.label} must be a switch")
        return errors

    def members(self, v: dict) -> list[tuple[str, str]]:
        """The (device id, entity key) pairs this combined device is made from."""
        return [(v[f"{i.key}_device"], v[f"{i.key}_key"]) for i in self.inputs if i.kind != "number"]

    # --- what it does

    def flow(self, cid: str, name: str, v: dict) -> dict | None:
        """The flow file content that does the work (see flowfiles.py), or None when no flow is needed."""
        return None

    def entity(self, item: dict, hub: Hub, old: Entity | None) -> Entity:
        raise NotImplementedError

    async def command(self, adapter, item: dict, on: bool | None, toggle: bool, extra: dict) -> None:
        raise ValueError("This cannot be controlled")


def _member(hub: Hub, v: dict, name: str) -> Entity | None:
    device = hub.devices.get(v[f"{name}_device"])
    return device.entities.get(v[f"{name}_key"]) if device else None


class HeaterTemplate(Template):
    """A room sensor and a heater on a plug: keeps the room at a target temperature, with safety cut-offs."""
    id = "heater"
    name = "Heater"
    model = "Heater"
    help = ("Keeps a room at a temperature with a temperature sensor and a smart plug. Switches off when the heater "
            "has been on too long or the sensor goes quiet.")
    inputs = [
        Input("sensor", "sensor", "Temperature sensor", device_class="temperature"),
        Input("plug", "switch", "Smart plug with the heater"),
        Input("target", "number", "Target temperature (°C)", 20, min=5, max=30),
        Input("margin", "number", "Degrees either side of the target", 0.5, min=0.1, max=5),
        Input("max_on_minutes", "number", "Switch off after this many minutes of heating", 120, min=1, max=1440),
        Input("sensor_lost_minutes", "number", "Switch off when the sensor is silent for (minutes)", 15, min=1, max=1440),
    ]

    def flow(self, cid: str, name: str, v: dict) -> dict:
        """It starts switched off; the adapter switches it on while the device is set to heat."""
        plug = {"device_id": v["plug_device"], "key": v["plug_key"]}
        off = {"type": "action.device", "command": "off", **plug}
        return {
            "id": f"combined-{cid}", "name": f"{name} (combined)", "enabled": False,
            "nodes": {
                "temp": {"type": "trigger.thermostat", "device_id": v["sensor_device"], "key": v["sensor_key"],
                         "target": v["target"], "margin": v["margin"]},
                "on": {"type": "action.device", "command": "on", **plug},
                "off": dict(off),
                "limit": {"type": "action.timer", "minutes": v["max_on_minutes"], "restart": False},
                "limit_off": dict(off),
                "limit_tell": {"type": "action.notify", "title": f"{name} off", "priority": "high",
                               "message": f"The heater was on for {v['max_on_minutes']:g} minutes straight and has been switched off."},
                "seen": {"type": "trigger.state", "device_id": v["sensor_device"], "key": v["sensor_key"]},
                "lost": {"type": "action.timer", "minutes": v["sensor_lost_minutes"], "restart": True},
                "lost_off": dict(off),
                "lost_tell": {"type": "action.notify", "title": f"{name} off", "priority": "high",
                              "message": "The temperature sensor stopped reporting, so the heater was switched off."},
            },
            "edges": [
                {"from": "temp", "out": "cold", "to": "on"},
                {"from": "on", "to": "limit", "in": "start"},
                {"from": "temp", "out": "warm", "to": "off"},
                {"from": "off", "to": "limit", "in": "stop"},
                {"from": "limit", "to": "limit_off"},
                {"from": "limit_off", "to": "limit_tell"},
                {"from": "seen", "to": "lost", "in": "start"},
                {"from": "lost", "to": "lost_off"},
                {"from": "lost_off", "to": "lost_tell"},
            ],
            "layout": {},
        }

    def entity(self, item: dict, hub: Hub, old: Entity | None) -> Entity:
        v = item["values"]
        reading, plug = _member(hub, v, "sensor"), _member(hub, v, "plug")
        current = reading.state if reading and isinstance(reading.state, (int, float)) else None
        return Entity("climate", "climate", item["name"], state=v["target"], unit="°C",
                      attrs={"current": current, "mode": "heat" if item["enabled"] else "off", "modes": ["off", "heat"],
                             "min": 5, "max": 30, "step": 0.5, "heating": bool(plug and plug.state is True)})

    async def command(self, adapter, item: dict, on: bool | None, toggle: bool, extra: dict) -> None:
        if extra.get("value") is not None:
            item = adapter.save(self.id, item["name"], {**item["values"], "target": float(extra["value"])}, item["id"])
        if extra.get("mode") is not None:
            on = extra["mode"] != "off"
        elif toggle:
            on = not item["enabled"]
        if on is not None and on != item["enabled"]:
            adapter.set_enabled(item, on)
            if not on:  # a heater left on with nothing watching it would be unsafe
                await adapter.hub.command(item["values"]["plug_device"], item["values"]["plug_key"], on=False)


class TimerSwitchTemplate(Template):
    """A plug that switches itself off a while after it was switched on (a fan, a charger, a heater blanket)."""
    id = "timer_switch"
    name = "Timer switch"
    model = "Timer switch"
    always_on = True
    help = "A plug that switches itself off a set time after it was switched on, however it was switched on."
    inputs = [
        Input("plug", "switch", "Smart plug"),
        Input("minutes", "number", "Switch off after (minutes)", 30, min=1, max=1440),
    ]

    def flow(self, cid: str, name: str, v: dict) -> dict:
        plug = {"device_id": v["plug_device"], "key": v["plug_key"]}
        return {
            "id": f"combined-{cid}", "name": f"{name} (combined)", "enabled": True,
            "nodes": {
                "change": {"type": "trigger.state", **plug},
                "wait": {"type": "action.timer", "minutes": v["minutes"], "restart": True},
                "off": {"type": "action.device", "command": "off", **plug},
            },
            "edges": [
                {"from": "change", "out": "on", "to": "wait", "in": "start"},
                {"from": "change", "out": "off", "to": "wait", "in": "stop"},
                {"from": "wait", "to": "off"},
            ],
            "layout": {},
        }

    def entity(self, item: dict, hub: Hub, old: Entity | None) -> Entity:
        plug = _member(hub, item["values"], "plug")
        return Entity("switch", "switch", item["name"], state=plug.state if plug else None)

    async def command(self, adapter, item: dict, on: bool | None, toggle: bool, extra: dict) -> None:
        v = item["values"]
        await adapter.hub.command(v["plug_device"], v["plug_key"], on=on, toggle=toggle)


class ThresholdTemplate(Template):
    """A reading turned into on/off: humidity above 70 %, a room above 26 °C. It switches back with some room."""
    id = "threshold"
    name = "Threshold sensor"
    model = "Threshold sensor"
    always_on = True
    help = "Turns a sensor reading into a yes/no, for example 'too humid'. Use it in flows and on the dashboard."
    inputs = [
        Input("sensor", "sensor", "Sensor"),
        Input("above", "number", "On above", 70, min=-1000, max=1000),
        Input("margin", "number", "Off again below (this many under)", 2, min=0, max=100),
    ]

    def entity(self, item: dict, hub: Hub, old: Entity | None) -> Entity:
        v = item["values"]
        reading = _member(hub, v, "sensor")
        value = reading.state if reading and isinstance(reading.state, (int, float)) and not isinstance(reading.state, bool) else None
        state = old.state if old else None  # between the two limits it stays as it was
        if value is not None:
            if value > v["above"]:
                state = True
            elif value < v["above"] - v["margin"]:
                state = False
            elif state is None:
                state = False
        unit = reading.unit if reading else None
        return Entity("on", "binary_sensor", item["name"], state=state, unit=unit, attrs={"value": value, "above": v["above"]})


TEMPLATES = {t.id: t for t in (HeaterTemplate(), TimerSwitchTemplate(), ThresholdTemplate())}
