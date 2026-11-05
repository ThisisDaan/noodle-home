import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from noodle import config, integrations, plugins  # noqa: E402


def test_discover_order_and_unique_ids():
    found = plugins.discover()
    assert [p.id for p in found if p.visible] == ["zigbee", "matter", "hue", "lifx", "shelly", "wled", "kasa", "sonos", "ble", "nanoleaf", "mqtt", "homeassistant", "dirigera", "ntfy", "system"]
    assert len({p.id for p in found}) == len(found)


def test_plugin_fields_and_forget_are_known_settings():
    for plugin in plugins.discover():
        for key in [f.key for f in plugin.fields] + plugin.forget:
            assert key in config.SETTINGS, f"{plugin.id}: {key} is not in config.SETTINGS"


def test_every_adapter_source_is_registered():
    from noodle import main
    assert set(main.ADAPTERS) == {"zigbee", "matter", "ble", "hue", "lifx", "group", "phone", "shelly", "wled", "kasa", "sonos", "nanoleaf", "mqtt", "homeassistant", "dirigera"}
    assert main.ADAPTERS["zigbee"] is main.zigbee and main.hub.adapters.keys() >= main.ADAPTERS.keys()


def test_default_added_is_what_was_set_up(monkeypatch):
    monkeypatch.setattr(config, "SETUP_DONE", True)  # a hub from before the wizard
    monkeypatch.setattr(config, "INTEGRATIONS", [])
    monkeypatch.setattr(config, "HUE_HOST", "")
    monkeypatch.setattr(config, "BLE_SENSORS", {})
    monkeypatch.setattr(config, "NTFY_TOPIC", "")
    assert integrations.added_ids() == ["zigbee", "matter"]
    monkeypatch.setattr(config, "HUE_HOST", "1.2.3.4")
    monkeypatch.setattr(config, "NTFY_TOPIC", "t")
    assert integrations.added_ids() == ["zigbee", "matter", "hue", "ntfy"]


def test_plugin_routes_are_mounted_and_need_login():
    from noodle import main
    paths = {r.path for r in main.app.routes}
    for path in ("/api/zigbee/permit_join", "/api/matter/commission",
                 "/api/ble/nearby", "/api/ble/sensors", "/api/ble/sensors/{address}"):
        assert path in paths, path
    client = TestClient(main.app)  # no lifespan: nothing connects
    assert client.get("/api/ble/nearby").status_code == 401
    assert client.post("/api/integrations/hue/search").status_code == 401
    assert client.get("/api/integrations").status_code == 401


def test_flow_nodes_come_from_plugins():
    assert set(plugins.node_types()) == {"action.notify", "action.speak"}


def test_flow_nodes_endpoint_needs_login_and_lists_nodes():
    from noodle import main
    assert TestClient(main.app).get("/api/flow/nodes").status_code == 401
    nodes = {n["type"]: n for n in main.flow_nodes()}
    assert nodes["action.notify"]["available"] and nodes["action.notify"]["fields"][0]["type"] == "select"
    assert nodes["action.speak"]["summary"] == "{speaker}: {message}"


def test_plugin_node_runs_through_the_engine(monkeypatch):
    import asyncio

    from noodle import main
    from noodle.plugins import base

    ran = []

    async def run(n):
        ran.append(n.fill("{count} presses"))
        n.log("ran")
        await n.follow()

    monkeypatch.setitem(plugins.node_types(), "action.speak", (None, base.Node("action.speak", "Speak", "action", run)))
    flow = {"id": "t", "name": "t", "enabled": True, "graph": {"nodes": [{"id": "a", "type": "action.speak", "data": {}}],
                                                              "edges": []}}
    asyncio.run(main.flows._step(flow, flow["graph"]["nodes"][0], {"count": 3}, [0]))
    assert ran == ["3 presses"] and main.flows.logs["t"][-1]["message"] == "ran"


def test_integrations_tell_the_page_which_panel_and_icon_to_use():
    from noodle import main
    described = {i.id: main._describe(i) for i in main._integrations()}
    assert described["hue"]["panel"] is None and described["hue"]["searchable"] is True and described["hue"]["press_hint"]
    assert described["ble"]["panel"] == "ble" and "sensors" in described["ble"]
    assert described["ntfy"]["panel"] == "notify" and described["zigbee"]["panel"] == "zigbee" and described["matter"]["panel"] == "matter"
    assert all(d["icon"] for d in described.values())


def test_system_page_info_comes_from_the_plugins(monkeypatch):
    import asyncio

    from noodle import main
    from noodle.adapters import otbr

    async def no_thread():
        return {"reachable": False}

    monkeypatch.setattr(otbr, "status", no_thread)
    zigbee = plugins.discover()[0].system_info(main.zigbee)
    assert zigbee["connected"] is False and "online" in zigbee
    matter = asyncio.run(next(p for p in plugins.discover() if p.id == "matter").system_info(main.matter))
    assert matter["connected"] is False and "sdk_version" in matter and matter["thread"] == {"reachable": False}


def test_every_searchable_integration_describes_the_same_search(monkeypatch):
    from noodle import main
    searchable = {p.id: p for p in plugins.discover() if p.searchable}
    assert {"hue", "zigbee", "ble", "lifx"} <= set(searchable)
    for plugin in searchable.values():
        assert plugin.noun and plugin.noun != "devices", plugin.id
    assert plugins.discover() and next(p for p in searchable.values() if p.id == "zigbee").name == "Zigbee2MQTT"


def test_a_button_device_answers_409_until_pressed(monkeypatch):
    import asyncio
    from noodle import main
    from noodle.plugins import PressButton
    hue = next(p for p in main.PLUGINS if p.id == "hue")
    calls = []

    async def add_found(adapter, key):
        calls.append(key)
        if len(calls) < 2:
            raise PressButton("Press the round button on top of the Hue bridge.")

    monkeypatch.setattr(hue, "add_found", add_found)
    monkeypatch.setattr(main.integrations, "added_ids", lambda: ["hue"])

    async def go():
        try:
            await main.add_found("hue", "10.0.0.2")
        except main.HTTPException as err:
            assert err.status_code == 409
        else:
            raise AssertionError("expected 409")
        assert (await main.add_found("hue", "10.0.0.2"))["id"] == "hue"

    real = asyncio.sleep
    monkeypatch.setattr(main, "restart_adapter", lambda s: real(0))
    real_sleep = asyncio.sleep
    monkeypatch.setattr(main.asyncio, "sleep", lambda s: real_sleep(0))
    asyncio.run(go())


def test_ntfy_timeout_is_retried_and_explained(monkeypatch):
    import asyncio

    import httpx

    from noodle import config, notify
    monkeypatch.setattr(config, "NTFY_TOPIC", "t")
    calls = []

    class Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw):
            calls.append(1)
            raise httpx.ConnectTimeout("")

    monkeypatch.setattr(notify.httpx, "AsyncClient", Client)
    try:
        asyncio.run(notify._ntfy("m", "t", "default", "", None))
    except RuntimeError as err:
        assert "Could not reach ntfy" in str(err) and "ConnectTimeout" in str(err)
    else:
        raise AssertionError("expected an error")
    assert len(calls) == 2


def test_a_simulated_button_press_runs_like_a_real_one(monkeypatch):
    from noodle import main
    from noodle.hub import Device, Entity
    device = Device(id="test:btn", source="zigbee", name="Remote",
                    entities={"action": Entity(key="action", kind="button", name="Button", actions=["single", "hold"])})
    main.hub.devices[device.id] = device
    seen = []
    main.hub.on_event(lambda d, key, action, data: seen.append((d.id, key, action, data)))
    try:
        main.press_button("test:btn", "action", main.PressBody(action="hold"))
        assert device.entities["action"].state == "hold"
        assert seen == [("test:btn", "action", "hold", {"simulated": True})]
        try:
            main.press_button("test:btn", "action", main.PressBody(action="triple"))
        except main.HTTPException as err:
            assert err.status_code == 400
        else:
            raise AssertionError("expected 400")
    finally:
        del main.hub.devices[device.id]


def test_the_last_press_and_change_time_come_with_the_device():
    import time

    from noodle import main
    from noodle.hub import Device, Entity
    device = Device(id="test:t", source="zigbee", name="Remote", entities={
        "action": Entity(key="action", kind="button", name="Button", actions=["single"]),
        "occupancy": Entity(key="occupancy", kind="binary_sensor", name="Motion", state=True, device_class="occupancy")})
    main.hub.upsert(device)
    try:
        assert device.entities["occupancy"].changed and device.entities["action"].changed is None
        before = time.time()
        main.hub.event(device, "action", "single")
        assert device.entities["action"].changed >= before
        assert main.hub.store.since("test:t", "action")[0] == "'single'"
        fresh = Device(id="test:t", source="zigbee", name="Remote", entities={"action": Entity(key="action", kind="button", name="Button")})
        main.hub.upsert(fresh)  # an adapter reloading the device list, or a restart
        assert fresh.entities["action"].changed == device.entities["action"].changed and fresh.entities["action"].state == "single"
    finally:
        main.hub.remove("test:t")


def test_bilresa_first_input_of_a_profile_turns_up():
    from noodle.adapters.matter import REMOTE_LAYOUTS
    layout = REMOTE_LAYOUTS["BILRESA"]
    assert layout["roles"][0][0] == "Dimmer increase" and layout["roles"][1][0] == "Dimmer decrease"
    # listed as down, up, button
    assert [layout["roles"][i][0] for i in layout["show"]] == ["Dimmer decrease", "Dimmer increase", "Button"]


def test_last_change_comes_from_history_when_a_sensor_has_not_reported_since_a_restart():
    from noodle import main
    from noodle.hub import Device, Entity
    main.hub.store.add_history("test:pir", "occupancy", True)
    main.hub.store.add_history("test:pir", "action", "single")
    device = Device(id="test:pir", source="zigbee", name="Motion", entities={
        "occupancy": Entity(key="occupancy", kind="binary_sensor", name="Motion", device_class="occupancy"),  # state unknown
        "action": Entity(key="action", kind="button", name="Button")})
    main.hub.upsert(device)
    try:
        assert device.entities["occupancy"].state is None and device.entities["occupancy"].changed
        assert device.entities["action"].changed and device.entities["action"].state == "single"
    finally:
        main.hub.remove("test:pir")


def test_an_unknown_sensor_state_shows_the_last_known_one():
    from noodle import main
    from noodle.hub import Device, Entity
    main.hub.store.add_history("test:k", "occupancy", False)
    device = Device(id="test:k", source="zigbee", name="Motion", entities={
        "occupancy": Entity(key="occupancy", kind="binary_sensor", name="Motion", device_class="occupancy")})
    main.hub.upsert(device)
    try:
        assert device.entities["occupancy"].state is None and device.entities["occupancy"].last is False
    finally:
        main.hub.remove("test:k")


def test_dimmer_inputs_get_a_direction_whatever_the_brand_calls_them():
    from noodle.hub import Entity
    role = lambda key, name: Entity(key=key, kind="button", name=name).role
    assert role("button_1", "Dimmer increase") == "increase" and role("button_2", "Dimmer decrease") == "decrease"
    assert role("up", "Brighter") == "increase" and role("down", "Dimmer") == "decrease"
    assert role("button_3", "Button") is None and role("on", "On") is None and role("off", "Off") is None
    assert Entity(key="up", kind="sensor", name="Up").role is None
