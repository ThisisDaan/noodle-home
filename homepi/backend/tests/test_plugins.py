import os
import tempfile

os.environ.setdefault("HOMEPI_DATA", tempfile.mkdtemp())
os.environ["HOMEPI_AUTOMATIONS"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from homepi import config, integrations, plugins  # noqa: E402


def test_discover_order_and_unique_ids():
    found = plugins.discover()
    assert [p.id for p in found if p.visible] == ["zigbee", "matter", "thermostat", "hue", "ble", "ntfy", "system"]
    assert len({p.id for p in found}) == len(found)


def test_plugin_fields_and_forget_are_known_settings():
    for plugin in plugins.discover():
        for key in [f.key for f in plugin.fields] + plugin.forget:
            assert key in config.SETTINGS, f"{plugin.id}: {key} is not in config.SETTINGS"


def test_every_adapter_source_is_registered():
    from homepi import main
    assert set(main.ADAPTERS) == {"zigbee", "matter", "ble", "thermostat", "hue", "group", "phone"}
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
    from homepi import main
    paths = {r.path for r in main.app.routes}
    for path in ("/api/zigbee/permit_join", "/api/matter/commission", "/api/hue/discover", "/api/hue/pair",
                 "/api/ble/nearby", "/api/ble/sensors", "/api/ble/sensors/{address}"):
        assert path in paths, path
    client = TestClient(main.app)  # no lifespan: nothing connects
    assert client.get("/api/ble/nearby").status_code == 401
    assert client.post("/api/hue/discover").status_code == 401
    assert client.get("/api/integrations").status_code == 401


def test_flow_nodes_come_from_plugins():
    assert set(plugins.node_types()) == {"action.notify", "action.speak"}


def test_flow_nodes_endpoint_needs_login_and_lists_nodes():
    from homepi import main
    assert TestClient(main.app).get("/api/flow/nodes").status_code == 401
    nodes = {n["type"]: n for n in main.flow_nodes()}
    assert nodes["action.notify"]["available"] and nodes["action.notify"]["fields"][0]["type"] == "select"
    assert nodes["action.speak"]["summary"] == "{speaker}: {message}"


def test_plugin_node_runs_through_the_engine(monkeypatch):
    import asyncio

    from homepi import main
    from homepi.plugins import base

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
    from homepi import main
    described = {i.id: main._describe(i) for i in main._integrations()}
    assert described["hue"]["panel"] == "hue" and described["hue"]["custom_form"] is True
    assert described["ble"]["panel"] == "ble" and "sensors" in described["ble"]
    assert described["ntfy"]["panel"] == "notify" and described["zigbee"]["panel"] is None
    assert all(d["icon"] for d in described.values())


def test_system_page_info_comes_from_the_plugins(monkeypatch):
    import asyncio

    from homepi import main
    from homepi.adapters import otbr

    async def no_thread():
        return {"reachable": False}

    monkeypatch.setattr(otbr, "status", no_thread)
    zigbee = plugins.discover()[0].system_info(main.zigbee)
    assert zigbee["connected"] is False and "online" in zigbee
    matter = asyncio.run(next(p for p in plugins.discover() if p.id == "matter").system_info(main.matter))
    assert matter["connected"] is False and "sdk_version" in matter and matter["thread"] == {"reachable": False}
