import asyncio
import json

import pytest

from noodle import capabilities
from noodle.plugins.zigbee.adapter import ZigbeeAdapter
from noodle.hub import Device, Entity, Hub
from noodle.store import Store


# --- capabilities

def test_clean_extra_accepts_what_a_kind_has():
    assert capabilities.clean_extra("light", {"color_temp": 2700, "color": {"h": 120, "s": 50}, "mode": None}) == {
        "color_temp": 2700, "color": {"h": 120.0, "s": 50.0}}
    assert capabilities.clean_extra("cover", {"action": "open"}) == {"action": "open"}
    assert capabilities.clean_extra("cover", {"position": 40}) == {"position": 40.0}
    assert capabilities.clean_extra("climate", {"value": 21.5, "mode": "heat"}) == {"value": 21.5, "mode": "heat"}


@pytest.mark.parametrize("kind, extra", [
    ("switch", {"color_temp": 2700}),   # a plug has no colour
    ("light", {"action": "open"}),      # a light does not open
    ("cover", {"action": "lock"}),      # wrong action for the kind
    ("lock", {"action": "stop"}),
    ("cover", {"position": 140}),       # out of range
    ("light", {"color": {"h": 10}}),    # saturation missing
    ("sensor", {"value": 1}),           # read only
])
def test_clean_extra_rejects(kind, extra):
    with pytest.raises(ValueError):
        capabilities.clean_extra(kind, extra)


def test_xy_to_hs_known_colours():
    red = capabilities.xy_to_hs(0.64, 0.33)
    green = capabilities.xy_to_hs(0.30, 0.60)
    assert red["h"] < 10 or red["h"] > 350
    assert 100 < green["h"] < 140
    assert capabilities.xy_to_hs(0.3127, 0.3290)["s"] < 10  # white


# --- the Zigbee adapter reads the whole exposes list and sends the new commands

EXPOSES = [
    {"type": "light", "features": [
        {"name": "state", "property": "state"}, {"name": "brightness", "property": "brightness"},
        {"name": "color_temp", "property": "color_temp", "value_min": 153, "value_max": 500},
        {"name": "color_xy", "property": "color", "type": "composite"}]},
    {"type": "cover", "features": [{"name": "state", "property": "state"}, {"name": "position", "property": "position"}]},
    {"type": "lock", "features": [{"name": "state", "property": "state"}]},
    {"type": "fan", "features": [{"name": "state", "property": "state"},
                                 {"name": "mode", "property": "mode", "values": ["low", "high"]}]},
    {"type": "climate", "features": [
        {"name": "occupied_heating_setpoint", "property": "occupied_heating_setpoint", "value_min": 5, "value_max": 30,
         "value_step": 0.5, "unit": "°C"},
        {"name": "system_mode", "property": "system_mode", "values": ["off", "heat"]}]},
]


class FakeClient:
    def __init__(self):
        self.sent = []

    async def publish(self, topic, payload):
        self.sent.append((topic, json.loads(payload)))


def setup(tmp_path, exposes):
    hub = Hub(Store(tmp_path / "db.sqlite"))
    adapter = ZigbeeAdapter(hub)
    hub.register(adapter)
    adapter.client = FakeClient()
    adapter.friendly["zigbee:x"] = "thing"
    device = Device(id="zigbee:x", source="zigbee", name="Thing", entities=adapter._entities(exposes))
    hub.devices[device.id] = device
    return hub, adapter, device


def test_exposes_become_kinds(tmp_path):
    _, _, device = setup(tmp_path, EXPOSES)
    assert {k: e.kind for k, e in device.entities.items()} == {
        "light": "light", "cover": "cover", "lock": "lock", "fan": "fan", "climate": "climate"}
    light = device.entities["light"]
    assert light.attrs["can"] == ["color_temp", "color"]
    assert light.attrs["color_temp_range"] == [2000, 6536]  # mireds 500..153 as kelvin
    assert device.entities["fan"].attrs["modes"] == ["low", "high"]
    assert device.entities["climate"].attrs["target_property"] == "occupied_heating_setpoint"


def test_state_reports_fill_entities(tmp_path):
    _, adapter, device = setup(tmp_path, EXPOSES)
    adapter._apply_state(device, {
        "state": "ON", "brightness": 127, "color_temp": 370, "color": {"x": 0.64, "y": 0.33}, "position": 30,
        "lock_state": "locked", "mode": "high", "occupied_heating_setpoint": 21, "local_temperature": 19.5,
        "system_mode": "heat"})
    light = device.entities["light"]
    assert (light.state, light.brightness, light.attrs["color_temp"]) == (True, 50, 2703)
    assert light.attrs["color"]["s"] > 80
    assert (device.entities["cover"].state, device.entities["cover"].attrs["position"]) == ("open", 30)
    assert device.entities["lock"].state == "locked"
    assert device.entities["fan"].attrs["mode"] == "high"
    climate = device.entities["climate"]
    assert (climate.state, climate.attrs["current"], climate.attrs["mode"]) == (21, 19.5, "heat")


def run(coro):
    return asyncio.run(coro)


def test_commands_reach_zigbee2mqtt(tmp_path):
    hub, adapter, _ = setup(tmp_path, EXPOSES)
    sent = adapter.client.sent
    run(hub.command("zigbee:x", "light", color_temp=2700))
    assert sent[-1] == ("zigbee2mqtt/thing/set", {"color_temp": 370, "state": "ON"})
    run(hub.command("zigbee:x", "light", color={"h": 120, "s": 80}))
    assert sent[-1][1]["color"] == {"hue": 120.0, "saturation": 80.0}
    run(hub.command("zigbee:x", "cover", action="close"))
    assert sent[-1][1] == {"state": "CLOSE"}
    run(hub.command("zigbee:x", "cover", position=25))
    assert sent[-1][1] == {"position": 25}
    run(hub.command("zigbee:x", "lock", action="unlock"))
    assert sent[-1][1] == {"state": "UNLOCK"}
    run(hub.command("zigbee:x", "fan", mode="high"))
    assert sent[-1][1] == {"mode": "high"}
    run(hub.command("zigbee:x", "climate", value=22, mode="heat"))
    assert sent[-1][1] == {"occupied_heating_setpoint": 22.0, "system_mode": "heat"}


def test_the_basic_commands_still_work(tmp_path):
    hub, adapter, _ = setup(tmp_path, EXPOSES)
    run(hub.command("zigbee:x", "light", on=True, brightness=100))
    assert adapter.client.sent[-1][1] == {"state": "ON", "brightness": 254}
    run(hub.command("zigbee:x", "light", toggle=True))
    assert adapter.client.sent[-1][1] == {"state": "TOGGLE"}


def test_hub_refuses_what_a_kind_or_adapter_cannot_do(tmp_path):
    hub, adapter, device = setup(tmp_path, EXPOSES)
    with pytest.raises(ValueError):
        run(hub.command("zigbee:x", "lock", position=10))
    # A Hue-like adapter that declares no extra commands cannot be sent a colour.
    device.entities["bulb"] = Entity("bulb", "light", "Bulb")
    device.source = "hue"
    hub.adapters["hue"] = type("A", (), {"source": "hue"})()
    with pytest.raises(ValueError, match="cannot do: color_temp"):
        run(hub.command("zigbee:x", "bulb", color_temp=2700))
    with pytest.raises(ValueError):
        run(hub.command("zigbee:x", "light", color_temp=0))  # out of range, checked before any adapter
