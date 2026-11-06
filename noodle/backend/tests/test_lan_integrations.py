import asyncio
import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from noodle import config, main  # noqa: E402
from noodle.plugins.dirigera import adapter as dirigera  # noqa: E402
from noodle.plugins.homeassistant import adapter as homeassistant  # noqa: E402
from noodle.plugins.kasa import adapter as kasa  # noqa: E402
from noodle.plugins.mqtt import adapter as mqttdisc  # noqa: E402
from noodle.plugins.nanoleaf import adapter as nanoleaf  # noqa: E402
from noodle.plugins.shelly import adapter as shelly  # noqa: E402
from noodle.plugins.sonos import adapter as sonos  # noqa: E402
from noodle.plugins.base import PressButton  # noqa: E402
from noodle.plugins.wled import adapter as wled  # noqa: E402


class FakeHub:
    def __init__(self):
        self.devices = {}
        self.adapters = {}

    def upsert(self, device):
        self.devices[device.id] = device

    def changed(self, device):
        pass

    def remove(self, device_id):
        self.devices.pop(device_id, None)


def mock(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- Kasa

def test_kasa_scrambling_round_trips_and_matches_the_known_start():
    message = {"system": {"get_sysinfo": {}}}
    wire = kasa.encrypt(message)
    assert wire[:4] == (len(wire) - 4).to_bytes(4, "big") and wire[4:6] == bytes([0xD0, 0xF2])
    assert kasa.decrypt(wire[4:]) == message
    assert kasa.decrypt(kasa.encrypt(message, prefix=False)) == message


def test_kasa_plug_and_bulb_entities():
    plug = kasa.entities_from({"relay_state": 1})
    assert plug["switch"].state is True
    bulb = kasa.entities_from({"is_color": 1, "light_state": {"on_off": 1, "brightness": 40, "hue": 120, "saturation": 80, "color_temp": 0}})
    assert bulb["light"].brightness == 40 and bulb["light"].attrs["color"] == {"h": 120, "s": 80}
    off = kasa.entities_from({"light_state": {"on_off": 0, "dft_on_state": {"brightness": 70, "color_temp": 3000}}})
    assert off["light"].state is False and off["light"].brightness == 70


# --- Shelly

def test_shelly_gen1_and_gen2_entities():
    g1 = shelly.entities_gen1({"relays": [{"ison": True}], "meters": [{"power": 12.34}], "temperature": 40.2})
    assert g1["switch"].state is True and g1["power"].state == 12.3 and g1["temperature"].unit == "°C"
    g2 = shelly.entities_gen2({"switch:0": {"output": False, "apower": 0}, "switch:1": {"output": True, "apower": 5}})
    assert set(g2) == {"switch_1", "switch_2", "power"} and g2["switch_2"].state is True and g2["power"].state == 5


def test_shelly_add_read_and_command_over_http(monkeypatch):
    saved = {}
    monkeypatch.setattr(config, "save", lambda values: saved.update(values))
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/shelly":
            return httpx.Response(200, json={"mac": "AABBCCDDEEFF", "gen": 2, "model": "SNSW-001P16EU", "name": "Desk plug"})
        if request.url.path == "/rpc/Shelly.GetStatus":
            return httpx.Response(200, json={"switch:0": {"output": True, "apower": 30.0}})
        return httpx.Response(200, json={})

    async def go():
        hub = FakeHub()
        adapter = shelly.ShellyAdapter(hub)
        adapter.http, adapter.running = mock(handler), True
        key = await adapter.add_host("http://192.168.1.50/")
        assert key == "aabbccddeeff" and saved == {"shelly_devices": {"aabbccddeeff": "192.168.1.50"}}
        device = hub.devices["shelly:aabbccddeeff"]
        assert device.name == "Desk plug" and device.entities["switch"].state is True
        await adapter.command(device, device.entities["switch"], False, None, False)
        assert any("/rpc/Switch.Set" in c and "on=false" in c for c in calls)
        with pytest.raises(ValueError):
            await adapter.add_host("a=b")

    asyncio.run(go())


# --- WLED, Nanoleaf, Sonos

def test_wled_light_and_colour_maths():
    light = wled.light_entity({"on": True, "bri": 128, "seg": [{"col": [[255, 0, 0]]}]})
    assert light.state is True and light.brightness == 50 and light.attrs["color"] == {"h": 0.0, "s": 100.0}
    assert wled.hs_to_rgb(120, 100) == [0, 255, 0]


def test_nanoleaf_light_entity():
    e = nanoleaf.light_entity({"on": {"value": True}, "brightness": {"value": 60}, "hue": {"value": 200}, "sat": {"value": 50},
                               "ct": {"value": 3000, "min": 1200, "max": 6500}})
    assert e.state is True and e.brightness == 60 and e.attrs["color_temp_range"] == [1200, 6500]


def test_nanoleaf_pairing_needs_the_button(monkeypatch):
    monkeypatch.setattr(config, "save", lambda values: None)

    async def go():
        adapter = nanoleaf.NanoleafAdapter(FakeHub())
        adapter.http = mock(lambda request: httpx.Response(403))
        with pytest.raises(PressButton, match="power button"):
            await adapter.add_host("192.168.1.60")

    asyncio.run(go())


def test_sonos_soap_helpers():
    xml = sonos.envelope(sonos.RENDERING[1], "SetVolume", {"InstanceID": 0, "Channel": "Master", "DesiredVolume": 30})
    assert "<DesiredVolume>30</DesiredVolume>" in xml and "RenderingControl:1" in xml
    assert sonos.tag("<a><CurrentVolume>17</CurrentVolume></a>", "CurrentVolume") == "17"


# --- MQTT discovery

def test_mqtt_abbreviations_templates_and_base_topic():
    cfg = mqttdisc.expand({"~": "tele/x", "stat_t": "~/STATE", "cmd_t": "cmnd/x/POWER", "val_tpl": "{{value_json.POWER}}",
                           "dev": {"ids": ["a1"], "mdl": "Plug"}})
    assert cfg["state_topic"] == "tele/x/STATE" and cfg["device"]["identifiers"] == ["a1"] and cfg["device"]["model"] == "Plug"
    assert mqttdisc.extract(cfg["value_template"], '{"POWER": "ON"}') == "ON"
    assert mqttdisc.extract("{{ value_json['a'].b }}", '{"a": {"b": 3}}') == 3
    assert mqttdisc.extract(None, "21.5") == "21.5"


def test_mqtt_device_is_found_updated_and_commanded():
    async def go():
        hub = FakeHub()
        adapter = mqttdisc.MqttAdapter(hub)
        sent = []

        class Client:
            async def publish(self, topic, payload):
                sent.append((topic, payload))

            async def subscribe(self, topic):
                pass

        adapter.client = Client()
        payload = (b'{"name":"Plug","stat_t":"tele/p/STATE","cmd_t":"cmnd/p/POWER","val_tpl":"{{value_json.POWER}}",'
                   b'"pl_on":"ON","pl_off":"OFF","uniq_id":"p1","dev":{"ids":["tasmota_p1"],"name":"Desk plug","mf":"Tasmota"}}')
        await adapter._handle("homeassistant/switch/plug1/config", payload)
        device = hub.devices["mqtt:tasmota_p1"]
        assert device.name == "Desk plug" and device.manufacturer == "Tasmota"
        await adapter._handle("tele/p/STATE", b'{"POWER":"ON"}')
        assert device.entities["plug1"].state is True
        await adapter.command(device, device.entities["plug1"], None, None, True)
        assert sent == [("cmnd/p/POWER", "OFF")]
        await adapter._handle("homeassistant/switch/z/config",
                              b'{"name":"z","dev":{"ids":["zigbee2mqtt_0x1"]},"stat_t":"zigbee2mqtt/z"}')
        assert "mqtt:zigbee2mqtt_0x1" not in hub.devices  # the Zigbee integration has those

    asyncio.run(go())


# --- Home Assistant, DIRIGERA

def test_home_assistant_states_and_services():
    light = homeassistant.entity_from_state({"entity_id": "light.kitchen", "state": "on", "attributes": {
        "friendly_name": "Kitchen", "brightness": 255, "supported_color_modes": ["color_temp", "hs"], "hs_color": [30, 50]}})
    assert light.key == "light__kitchen" and light.brightness == 100 and light.attrs["can"] == ["color_temp", "color"]
    sensor = homeassistant.entity_from_state({"entity_id": "sensor.t", "state": "21.456", "attributes": {"unit_of_measurement": "°C"}})
    assert sensor.state == 21.46
    assert homeassistant.entity_from_state({"entity_id": "automation.x", "state": "on"}) is None
    assert homeassistant.service_for("light", "light.k", None, 30, False, {}) == ("light", "turn_on", {"brightness_pct": 30})
    assert homeassistant.service_for("switch", "switch.s", False, None, False, {}) == ("switch", "turn_off", {})
    assert homeassistant.service_for("cover", "cover.c", None, None, False, {"action": "stop"})[1] == "stop_cover"


def test_dirigera_devices_and_pairing_challenge():
    light = dirigera.entities_from({"deviceType": "light", "attributes": {
        "isOn": True, "lightLevel": 80, "colorTemperature": 3000, "colorTemperatureMin": 4000,
        "colorTemperatureMax": 2202, "batteryPercentage": 90}})
    assert light["light"].brightness == 80 and light["light"].attrs["color_temp_range"] == [2202, 4000]
    assert light["battery_level"].state == 90
    blind = dirigera.entities_from({"deviceType": "blinds", "attributes": {"blindsCurrentLevel": 25}})
    assert blind["cover"].attrs["position"] == 75  # 25 % closed = 75 open
    assert dirigera.entities_from({"deviceType": "shortcutController", "attributes": {}}) == {}
    assert dirigera.challenge("abc") == "ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0"


# --- routes

def test_new_integration_routes_need_a_login():
    client = TestClient(main.app)
    paths = {r.path for r in main.app.routes}
    for path in ("/api/shelly/devices", "/api/wled/devices/{key}", "/api/kasa/devices", "/api/sonos/devices",
                 "/api/nanoleaf/devices", "/api/dirigera/pair"):
        assert path in paths, path
    assert client.post("/api/shelly/devices", json={"host": "1.2.3.4"}).status_code == 401
    assert client.delete("/api/wled/devices/x").status_code == 401
    assert client.post("/api/dirigera/pair", json={"host": "1.2.3.4"}).status_code == 401


def test_home_assistant_buttons_battery_and_diagnostics():
    class Hub(FakeHub):
        def __init__(self):
            super().__init__()
            self.events = []

        def event(self, device, key, action, data=None):
            self.events.append((device.id, key, action))

    hub = Hub()
    adapter = homeassistant.HomeAssistantAdapter(hub)
    adapter.devices_reg = {"d1": {"id": "d1", "name": "Wall switch", "model": "Wall switch"}}
    adapter.registry = {
        "event.wall_switch_action": {"entity_id": "event.wall_switch_action", "device_id": "d1"},
        "sensor.wall_switch_battery": {"entity_id": "sensor.wall_switch_battery", "device_id": "d1", "entity_category": "diagnostic"},
        "sensor.wall_switch_device_temperature": {"entity_id": "sensor.wall_switch_device_temperature", "device_id": "d1", "entity_category": "diagnostic"},
        "event.backup": {"entity_id": "event.backup"},
    }
    event = {"entity_id": "event.wall_switch_action", "state": "2026-11-05T10:00:00", "attributes": {"event_types": ["on", "off"], "event_type": "on"}}
    adapter._apply(event)
    adapter._apply({"entity_id": "sensor.wall_switch_battery", "state": "83", "attributes": {"device_class": "battery", "unit_of_measurement": "%"}})
    adapter._apply({"entity_id": "sensor.wall_switch_device_temperature", "state": "22", "attributes": {"device_class": "temperature"}})
    adapter._apply({"entity_id": "event.backup", "state": "2026-11-05T10:00:00", "attributes": {"event_types": ["completed"]}})
    device = hub.devices["homeassistant:d1"]
    assert list(device.entities) == ["event__wall_switch_action"] and device.entities["event__wall_switch_action"].kind == "button"
    assert device.battery == 83 and len(hub.devices) == 1
    assert hub.events == []  # what was already there is not a press
    adapter.live = True
    adapter._apply({**event, "state": "2026-11-05T10:05:00", "attributes": {**event["attributes"], "event_type": "off"}})
    assert hub.events == [("homeassistant:d1", "event__wall_switch_action", "off")]


def test_a_dimmable_light_keeps_its_brightness_when_off():
    off = homeassistant.entity_from_state({"entity_id": "light.a", "state": "off", "attributes": {"supported_color_modes": ["brightness"]}})
    assert off.brightness == 0
    plain = homeassistant.entity_from_state({"entity_id": "light.b", "state": "off", "attributes": {"supported_color_modes": ["onoff"]}})
    assert plain.brightness is None
    assert mqttdisc.MqttAdapter._entity("light", "l", {"brightness_command_topic": "x/bri"}).brightness == 0
    assert mqttdisc.MqttAdapter._entity("light", "l", {}).brightness is None


def test_a_device_home_assistant_has_no_state_for_is_not_off():
    hub = FakeHub()
    adapter = homeassistant.HomeAssistantAdapter(hub)
    adapter.devices_reg = {"p": {"id": "p", "name": "Blanket plug"}}
    adapter.registry = {e: {"entity_id": e, "device_id": "p"} for e in ("switch.blanket", "sensor.blanket_power")}
    adapter._apply({"entity_id": "switch.blanket", "state": "unknown", "attributes": {}})
    adapter._apply({"entity_id": "sensor.blanket_power", "state": "unknown", "attributes": {"device_class": "power", "unit_of_measurement": "W"}})
    device = hub.devices["homeassistant:p"]
    assert device.entities["switch__blanket"].state is None and device.available is False
    adapter._apply({"entity_id": "switch.blanket", "state": "on", "attributes": {}})
    adapter._apply({"entity_id": "sensor.blanket_power", "state": "42.5", "attributes": {"device_class": "power", "unit_of_measurement": "W"}})
    assert device.entities["switch__blanket"].state is True and device.available is True
