import asyncio
import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

import pytest  # noqa: E402

from noodle.hub import Hub  # noqa: E402
from noodle.plugins.custom.adapter import CustomAdapter  # noqa: E402
from noodle.store import Store  # noqa: E402

FIELDS = [{"label": "Heating", "type": "switch"}, {"label": "Target", "type": "number", "unit": "°C"},
          {"label": "Status", "type": "text"}]


@pytest.fixture
def adapter(tmp_path):
    hub = Hub(Store(tmp_path / "t.db"))
    return CustomAdapter(hub)


def test_a_custom_device_shows_up_with_one_entity_per_field(adapter):
    saved = adapter.save("Study heater", FIELDS)
    assert [f["key"] for f in saved["fields"]] == ["heating", "target", "status"]
    device = adapter.hub.devices[f"custom:{saved['id']}"]
    kinds = {k: (e.kind, e.state, e.unit) for k, e in device.entities.items()}
    assert kinds == {"heating": ("switch", False, None), "target": ("number", None, "°C"), "status": ("sensor", None, None)}
    assert device.source == "custom" and device.name == "Study heater"


def test_writes_fit_the_field_and_are_kept(adapter):
    saved = adapter.save("Study heater", FIELDS)
    did = saved["id"]
    assert adapter.write(did, "heating", "on") is True
    assert adapter.write(did, "target", "21.5") == 21.5
    assert adapter.write(did, "status", "Heating") == "Heating"
    entities = adapter.hub.devices[f"custom:{did}"].entities
    assert (entities["heating"].state, entities["target"].state, entities["status"].state) == (True, 21.5, "Heating")
    for bad in (("target", "warm"), ("target", True)):
        with pytest.raises(ValueError):
            adapter.write(did, *bad)
    with pytest.raises(KeyError):
        adapter.write(did, "nope", 1)
    # a new adapter on the same database (a restart) has the values
    again = CustomAdapter(adapter.hub)
    again._publish(again.devices[did])
    assert adapter.hub.devices[f"custom:{did}"].entities["target"].state == 21.5


def test_fields_can_be_changed_and_a_removed_field_loses_its_value(adapter):
    did = adapter.save("Study heater", FIELDS)["id"]
    adapter.write(did, "status", "Idle")
    adapter.save("Study heater", [{"key": "heating", "label": "Heating", "type": "switch"}], did)
    assert list(adapter.hub.devices[f"custom:{did}"].entities) == ["heating"]
    assert adapter._raw(did, "status") is None
    for bad in ([{"label": "", "type": "text"}], [{"label": "A", "type": "wheel"}],
                [{"label": "A", "type": "text"}, {"key": "a", "label": "B", "type": "text"}]):
        with pytest.raises(ValueError):
            adapter.save("X", bad)
    with pytest.raises(ValueError):
        adapter.save("  ", [])


def test_deleting_removes_the_device_and_its_values(adapter):
    did = adapter.save("Study heater", FIELDS)["id"]
    adapter.write(did, "heating", True)
    adapter.delete(did)
    assert f"custom:{did}" not in adapter.hub.devices and adapter._raw(did, "heating") is None
    with pytest.raises(KeyError):
        adapter.delete(did)


def test_the_device_can_be_switched_and_set_like_any_other(adapter):
    did = adapter.save("Study heater", FIELDS)["id"]
    device = adapter.hub.devices[f"custom:{did}"]
    asyncio.run(adapter.command(device, device.entities["heating"], None, None, True))
    assert device.entities["heating"].state is True
    asyncio.run(adapter.command(device, device.entities["target"], None, None, False, value=19))
    assert adapter.hub.devices[f"custom:{did}"].entities["target"].state == 19.0


def test_old_variables_move_into_the_variables_device_and_nothing_is_lost(tmp_path):
    store = Store(tmp_path / "old.db")
    store.set_var("washer.status", "Running")  # the shape a hub from before custom devices has
    store.set_var("post", "waiting")
    adapter = CustomAdapter(Hub(store))
    assert adapter.get_variable("washer.status") == "Running" and adapter.get_variable("post") == "waiting"
    assert set(adapter.variables()) == {"washer.status", "post"}
    assert store.get_var("post") == "waiting"  # the old table is untouched, so rolling back loses nothing
    # safe to run again: no duplicates, and a newer value is not overwritten by the old one
    adapter.set_variable("post", "collected")
    adapter._migrate_variables()
    again = CustomAdapter(Hub(store))
    again._migrate_variables()
    assert [f["key"] for f in again.devices["variables"]["fields"]].count("post") == 1
    assert again.get_variable("post") == "collected"


def test_the_variables_device_is_built_in_and_creates_fields_when_a_flow_uses_a_new_name(adapter):
    assert adapter.variables() == {}
    adapter.set_variable("status", "Heating")
    assert adapter.hub.devices["custom:variables"].entities["status"].state == "Heating"
    assert adapter.listing()[0]["builtin"] is True
    with pytest.raises(ValueError):
        adapter.delete("variables")


def test_flow_steps_write_to_entities_and_variables():
    from noodle import main
    adapter = main.ADAPTERS["custom"]
    did = adapter.save("Flow test device", FIELDS)["id"]
    flow = {"id": "t", "name": "t", "enabled": True, "graph": {"nodes": [], "edges": []}}
    write = {"id": "w", "type": "action.write", "data": {"device_id": f"custom:{did}", "key": "status", "value": "Heating"}}
    asyncio.run(main.flows._step(flow, write, {}, [0]))
    assert main.hub.devices[f"custom:{did}"].entities["status"].state == "Heating"
    var = {"id": "v", "type": "action.var", "data": {"name": "flow-test-var", "value": "yes"}}
    asyncio.run(main.flows._step(flow, var, {}, [0]))
    assert adapter.get_variable("flow-test-var") == "yes"
    assert main.flows._check("cond.var", {"name": "flow-test-var", "op": "eq", "value": "yes"}) is True
    elsewhere = {"id": "x", "type": "action.write", "data": {"device_id": "zigbee:nope", "key": "k", "value": "1"}}
    with pytest.raises(LookupError):
        asyncio.run(main.flows._step(flow, elsewhere, {}, [0]))
    adapter.delete(did)


def test_a_write_is_seen_by_the_flows_as_a_state_change(adapter):
    seen = []
    adapter.hub.on_state_change(lambda device, entity, old, new: seen.append((entity.key, old, new)))
    did = adapter.save("Study heater", FIELDS)["id"]
    adapter.write(did, "heating", True)
    assert ("heating", False, True) in seen


def test_the_routes_need_login():
    from fastapi.testclient import TestClient
    from noodle import main
    client = TestClient(main.app)
    assert client.get("/api/custom").status_code == 401
    assert client.post("/api/custom", json={"name": "x"}).status_code == 401


def test_number_fields_can_have_a_range_for_dials_and_sliders(adapter):
    did = adapter.save("Study heater", [{"label": "Target", "type": "number", "unit": "°C", "min": 5, "max": 30, "step": 0.5}])["id"]
    entity = adapter.hub.devices[f"custom:{did}"].entities["target"]
    assert entity.attrs == {"min": 5, "max": 30, "step": 0.5}
    for bad in ({"min": 10, "max": 5}, {"step": 0}, {"min": "low"}):
        with pytest.raises(ValueError):
            adapter.save("X", [{"label": "N", "type": "number", **bad}], did)
