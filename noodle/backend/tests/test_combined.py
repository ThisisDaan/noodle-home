import asyncio
import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

import pytest  # noqa: E402

from noodle import flowfiles  # noqa: E402
from noodle.hub import Device, Entity  # noqa: E402
from noodle.plugins.combined.templates import TEMPLATES  # noqa: E402

VALUES = {"sensor_device": "test:room", "sensor_key": "temperature", "plug_device": "test:plug", "plug_key": "switch"}


@pytest.fixture
def rig():
    from noodle import main
    main.hub.upsert(Device(id="test:room", source="test", name="Room",
                           entities={"temperature": Entity("temperature", "sensor", "Temp", state=17.0, unit="°C")}))
    main.hub.upsert(Device(id="test:plug", source="test", name="Plug",
                           entities={"switch": Entity("switch", "switch", "Switch", state=False)}))
    adapter = main.ADAPTERS["combined"]
    yield main, adapter
    for cid in list(adapter.items):
        adapter.delete(cid)


def test_the_generated_flow_is_a_valid_flow_file():
    values = TEMPLATES["heater"].clean(VALUES)
    doc = TEMPLATES["heater"].flow("abc", "Heater", values)
    errors, _ = flowfiles.validate(doc)
    assert errors == []
    assert doc["enabled"] is False  # a generated flow starts switched off


def test_save_validates_and_writes_a_file_and_a_flow(rig):
    main, adapter = rig
    with pytest.raises(ValueError):
        adapter.save("heater", "Bad", {**VALUES, "plug_device": "test:nope"})
    with pytest.raises(ValueError):
        adapter.save("heater", "Bad", {**VALUES, "target": 99})
    item = adapter.save("heater", "Study heater", VALUES)
    assert (adapter.dir / f"{item['id']}.yaml").exists()
    flow = main.flows.flows[f"combined-{item['id']}"]
    assert flow["enabled"] is False
    device = main.hub.devices[f"combined:{item['id']}"]
    assert device.entities["climate"].attrs["mode"] == "off" and device.entities["climate"].state == 20.0


def test_saving_twice_gives_the_same_flow(rig):
    main, adapter = rig
    item = adapter.save("heater", "Study heater", VALUES)
    first = flowfiles.content_key(main.flows.flows[f"combined-{item['id']}"])
    adapter.save("heater", "Study heater", VALUES, item["id"])
    assert flowfiles.content_key(main.flows.flows[f"combined-{item['id']}"]) == first


def test_turning_it_on_switches_the_flow_on_and_off_switches_the_plug_off(rig):
    main, adapter = rig
    item = adapter.save("heater", "Study heater", VALUES)
    device = main.hub.devices[f"combined:{item['id']}"]
    sent = []

    async def fake_command(device_id, key, **kwargs):
        sent.append((device_id, key, kwargs))
    main.hub.command_real, main.hub.command = main.hub.command, fake_command
    try:
        entity = device.entities["climate"]
        asyncio.run(adapter.command(device, entity, None, None, False, mode="heat"))
        assert main.flows.flows[f"combined-{item['id']}"]["enabled"] is True and not sent
        asyncio.run(adapter.command(device, entity, None, None, False, value=22))
        assert adapter.items[item["id"]]["values"]["target"] == 22.0
        assert main.flows.flows[f"combined-{item['id']}"]["enabled"] is True  # changing the target keeps it on
        asyncio.run(adapter.command(device, entity, None, None, False, mode="off"))
        assert main.flows.flows[f"combined-{item['id']}"]["enabled"] is False
        assert sent == [("test:plug", "switch", {"on": False})]
    finally:
        main.hub.command = main.hub.command_real


def test_deleting_removes_the_file_flow_and_device_but_not_the_members(rig):
    main, adapter = rig
    item = adapter.save("heater", "Study heater", VALUES)
    adapter.delete(item["id"])
    assert not (adapter.dir / f"{item['id']}.yaml").exists()
    assert f"combined-{item['id']}" not in main.flows.flows
    assert f"combined:{item['id']}" not in main.hub.devices
    assert "test:room" in main.hub.devices and "test:plug" in main.hub.devices


def test_routes_need_login():
    from fastapi.testclient import TestClient
    from noodle import main
    client = TestClient(main.app)
    assert client.get("/api/combined/templates").status_code == 401
    assert client.post("/api/combined", json={"template": "heater", "name": "x"}).status_code == 401


def test_a_file_edited_by_hand_is_picked_up_and_our_own_writes_are_not(rig):
    main, adapter = rig
    item = adapter.save("heater", "Study heater", VALUES)
    path = adapter.dir / f"{item['id']}.yaml"
    before = main.flows.flows[f"combined-{item['id']}"]["updated"]
    adapter.reload()  # nothing changed in the files since we wrote them
    assert main.flows.flows[f"combined-{item['id']}"]["updated"] == before
    path.write_text(path.read_text(encoding="utf-8").replace("target: 20.0", "target: 23.5"), encoding="utf-8")
    adapter.reload()
    assert adapter.items[item["id"]]["values"]["target"] == 23.5
    assert main.hub.devices[f"combined:{item['id']}"].entities["climate"].state == 23.5
    node = next(n for n in main.flows.flows[f"combined-{item['id']}"]["graph"]["nodes"] if n["id"] == "temp")
    assert node["data"]["target"] == 23.5
    path.write_text("id: " + item["id"] + "\ntemplate: nonsense\n", encoding="utf-8")
    adapter.reload()  # a broken file is ignored, the device keeps what it had
    assert adapter.items[item["id"]]["values"]["target"] == 23.5
    path.unlink()
    adapter.reload()
    assert item["id"] not in adapter.items and f"combined:{item['id']}" not in main.hub.devices


def test_every_template_makes_a_valid_flow_or_none(rig):
    main, adapter = rig
    for tpl in TEMPLATES.values():
        values = tpl.clean({**VALUES, **{"sensor_device": "test:room", "sensor_key": "temperature"}})
        doc = tpl.flow("abc", "X", values)
        if doc is not None:
            assert flowfiles.validate(doc)[0] == [], tpl.id


def test_timer_switch_mirrors_the_plug_and_forwards_commands(rig):
    main, adapter = rig
    item = adapter.save("timer_switch", "Fan timer", {"plug_device": "test:plug", "plug_key": "switch", "minutes": 45})
    device = main.hub.devices[f"combined:{item['id']}"]
    assert device.entities["switch"].state is False
    assert main.flows.flows[f"combined-{item['id']}"]["enabled"] is True  # no off position: it always runs
    sent = []

    async def fake_command(device_id, key, **kwargs):
        sent.append((device_id, key, kwargs))
    real, main.hub.command = main.hub.command, fake_command
    try:
        asyncio.run(adapter.command(device, device.entities["switch"], True, None, False))
    finally:
        main.hub.command = real
    assert sent == [("test:plug", "switch", {"on": True, "toggle": False})]
    flow = main.flows.flows[f"combined-{item['id']}"]
    assert next(n for n in flow["graph"]["nodes"] if n["id"] == "wait")["data"]["minutes"] == 45.0


def test_threshold_sensor_has_a_gap_before_it_switches_back(rig):
    main, adapter = rig
    item = adapter.save("threshold", "Too warm", {"sensor_device": "test:room", "sensor_key": "temperature",
                                                   "above": 20, "margin": 2})
    state = lambda: main.hub.devices[f"combined:{item['id']}"].entities["on"].state  # noqa: E731
    assert state() is False and main.flows.flows.get(f"combined-{item['id']}") is None  # no flow needed
    room = main.hub.devices["test:room"].entities["temperature"]
    room.state = 21.0
    adapter._member_changed(main.hub.devices["test:room"], room, 17.0, 21.0)
    assert state() is True
    room.state = 19.0  # below 20 but not below 18: stays on
    adapter._member_changed(main.hub.devices["test:room"], room, 21.0, 19.0)
    assert state() is True
    room.state = 17.5
    adapter._member_changed(main.hub.devices["test:room"], room, 19.0, 17.5)
    assert state() is False
    room.state = 17.0  # put the shared fake back
