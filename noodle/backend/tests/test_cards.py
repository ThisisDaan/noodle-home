import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

import pytest  # noqa: E402

from noodle import flowfiles  # noqa: E402

DOC = {
    "id": "card-test", "name": "Card test", "enabled": True,
    "card": {"title": "Study heater",
             "controls": [{"id": "heat", "type": "switch", "label": "Heating", "default": False},
                          {"id": "target", "type": "dial", "label": "Target", "min": 5, "max": 30, "step": 0.5, "default": 20}],
             "show": [{"type": "value", "label": "Now", "device_id": "t:room", "key": "temperature"},
                      {"type": "status", "label": "State", "variable": "card-test.status"}]},
    "nodes": {
        "temp": {"type": "trigger.thermostat", "device_id": "t:room", "key": "temperature", "target": "{control.target}", "margin": 0.5},
        "on": {"type": "trigger.control", "control": "heat"},
        "plug": {"type": "action.device", "command": "on", "device_id": "t:plug", "key": "switch"},
    },
    "edges": [{"from": "temp", "out": "cold", "to": "plug"}, {"from": "on", "out": "on", "to": "plug"}],
}


def doc(**changes):
    import copy
    d = copy.deepcopy(DOC)
    d.update(changes)
    return d


@pytest.fixture
def engine():
    from noodle import main
    flow = flowfiles.from_doc(DOC)
    main.flows.create(flow["name"], flow["graph"], enabled=True, flow_id=flow["id"])
    yield main.flows
    main.flows.delete("card-test")


def test_a_valid_card_has_no_errors():
    assert flowfiles.validate(DOC) == ([], [])


def test_card_mistakes_are_reported():
    bad = doc(card={"controls": [{"id": "Heat", "type": "switch"}, {"id": "x", "type": "wheel"},
                                 {"id": "d", "type": "dial", "min": 10, "max": 5}, {"id": "s", "type": "select"}],
                    "show": [{"type": "status"}, {"type": "value"}, {"type": "pie"}]})
    errors, _ = flowfiles.validate(bad)
    text = "\n".join(errors)
    for part in ("needs an id", "type must be one of", "min must be below max", "needs a list of options",
                 "a status needs a 'variable'", "needs a device_id and a key", "show 3"):
        assert part in text, part


def test_unknown_controls_are_errors_in_nodes():
    d = doc()
    d["nodes"]["on"] = {"type": "trigger.control", "control": "nope"}
    d["nodes"]["temp"] = {**d["nodes"]["temp"], "target": "{control.gone}"}
    errors, _ = flowfiles.validate(d)
    assert any("'nope' is not a control" in e for e in errors) and any("control 'gone'" in e for e in errors)


def test_the_card_survives_a_round_trip_and_a_written_file(tmp_path):
    flow = flowfiles.from_doc(DOC)
    assert flow["graph"]["card"]["title"] == "Study heater"
    assert flowfiles.to_doc(flow)["card"] == DOC["card"]
    files = flowfiles.FlowFiles(tmp_path)
    files.write(flow)
    loaded, errors, _ = files.read(tmp_path / "card-test.yaml")
    assert errors == [] and loaded["graph"]["card"] == DOC["card"]
    flow["graph"].pop("card")
    files.write(flow)
    assert "\ncard:" not in (tmp_path / "card-test.yaml").read_text(encoding="utf-8")


def test_the_editor_saving_a_graph_without_a_card_keeps_the_card(engine):
    graph = {"nodes": engine.flows["card-test"]["graph"]["nodes"], "edges": []}
    engine.update("card-test", graph=graph)
    assert engine.flows["card-test"]["graph"]["card"]["title"] == "Study heater"


def test_controls_hold_their_values_and_keep_them_in_range(engine):
    flow = engine.flows["card-test"]
    assert engine.control_value(flow, "heat") is False and engine.control_value(flow, "target") == 20
    assert engine.set_control("card-test", "target", 31) == 30  # kept inside min and max
    assert engine.set_control("card-test", "target", 21.3) == 21.5  # whole steps
    assert engine.control_value(flow, "target") == 21.5
    assert engine.set_control("card-test", "heat", True) is True and engine.control_value(flow, "heat") is True
    assert engine.store.get_var("card-test.heat") == "on"  # readable by "Check variable" nodes
    for bad in (("heat", "yes"), ("target", "hot"), ("target", True)):
        with pytest.raises(ValueError):
            engine.set_control("card-test", *bad)
    with pytest.raises(KeyError):
        engine.set_control("card-test", "nope", 1)


def test_a_control_starts_its_card_control_nodes_only_while_the_flow_is_on(engine):
    fired = []
    engine._fire = lambda flow, node, msg, handle="out": fired.append((node["id"], handle, msg["value"]))
    engine.set_control("card-test", "heat", True)
    assert fired == [("on", "out", True), ("on", "on", True)]
    fired.clear()
    engine.set_control("card-test", "target", 22)  # no card control node for this one
    assert fired == []
    engine.update("card-test", enabled=False)
    engine.set_control("card-test", "heat", False)
    assert fired == []  # a switched-off flow does nothing, but the value is kept
    assert engine.control_value(engine.flows["card-test"], "heat") is False


def test_a_thermostat_follows_the_target_control(engine):
    from noodle.hub import Device, Entity
    fired = []
    engine._fire = lambda flow, node, msg, handle="out": fired.append(handle)
    flow = engine.flows["card-test"]
    node = next(n for n in flow["graph"]["nodes"] if n["id"] == "temp")
    engine.set_control("card-test", "target", 20)
    engine._thermostat(flow, node, 19.0)
    assert fired == ["cold"]  # 19 is at or below 20 - 0.5
    fired.clear()
    engine.set_control("card-test", "target", 10)  # the target moved: decided again, now it is warm
    engine._thermostat(flow, node, 19.0)
    assert fired == ["warm"]
    assert engine.number(flow, {"minutes": "{control.target}"}, "minutes", 1) == 10.0
    assert engine.number(flow, {"minutes": 5}, "minutes", 1) == 5.0


def test_the_flow_summary_carries_the_card_and_the_api_needs_login(engine):
    from fastapi.testclient import TestClient
    from noodle import main
    assert next(f for f in engine.summary() if f["id"] == "card-test")["card"]["controls"][0]["id"] == "heat"
    assert TestClient(main.app).post("/api/flows/card-test/controls/heat", json={"value": True}).status_code == 401
