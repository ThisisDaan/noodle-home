from noodle import config
from noodle.flows import FlowEngine
from noodle.hub import Hub
from noodle.migrations import retire_thermostat
from noodle.store import Store

OLD = {"THERMOSTAT_SENSOR_DEVICE": "ble:AA:BB", "THERMOSTAT_SENSOR_KEY": "temperature",
       "THERMOSTAT_HEATER_DEVICE": "zigbee:0x1", "THERMOSTAT_HEATER_KEY": "switch",
       "THERMOSTAT_NAME": "Living room heating", "INTEGRATIONS": ["zigbee", "thermostat"]}


def setup(tmp_path, monkeypatch, **old):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "_SETTINGS", config.YamlFile(tmp_path / "config" / "settings.yaml"))
    monkeypatch.setattr(config, "_SECRETS", config.YamlFile(tmp_path / "config" / "secrets.yaml", private=True))
    for attr in ("THERMOSTAT_ID", "THERMOSTAT_NAME", "THERMOSTAT_SENSOR_DEVICE", "THERMOSTAT_SENSOR_KEY",
                 "THERMOSTAT_HEATER_DEVICE", "THERMOSTAT_HEATER_KEY", "INTEGRATIONS"):
        monkeypatch.setattr(config, attr, getattr(config, attr))  # so what the migration clears is put back after
    for attr, value in old.items():
        monkeypatch.setattr(config, attr, value)
    store = Store(tmp_path / "db.sqlite")
    return FlowEngine(Hub(store), store), store


def test_old_settings_become_a_switched_off_thermostat_flow(tmp_path, monkeypatch):
    engine, store = setup(tmp_path, monkeypatch, **OLD)
    store.set("thermostat_target", "19.5")
    retire_thermostat(engine)
    flow = engine.flows["thermostat"]
    assert flow["name"] == "Living room heating" and flow["enabled"] is False
    nodes = {n["id"]: n for n in flow["graph"]["nodes"]}
    assert nodes["room"]["type"] == "trigger.thermostat"
    assert nodes["room"]["data"] == {"device_id": "ble:AA:BB", "key": "temperature", "target": 19.5, "margin": 0.5}
    assert nodes["heat-on"]["data"]["device_id"] == "zigbee:0x1" and nodes["heat-on"]["data"]["inputs"] == ["on"]
    assert nodes["heat-off"]["data"]["inputs"] == ["off"]
    assert {(e["sourceHandle"], e["target"], e["targetHandle"]) for e in flow["graph"]["edges"]} == {
        ("cold", "heat-on", "on"), ("warm", "heat-off", "off")}
    assert (tmp_path / "config" / "flows" / "thermostat.yaml").exists()
    assert "thermostat" not in config.INTEGRATIONS and config.INTEGRATIONS == ["zigbee"]
    assert config.THERMOSTAT_SENSOR_DEVICE == "" and config.THERMOSTAT_HEATER_DEVICE == ""


def test_running_it_twice_changes_nothing(tmp_path, monkeypatch):
    engine, _ = setup(tmp_path, monkeypatch, **OLD)
    retire_thermostat(engine)
    flow = dict(engine.flows["thermostat"])
    path = tmp_path / "config" / "flows" / "thermostat.yaml"
    before = path.read_text()
    retire_thermostat(engine)
    assert engine.flows["thermostat"] == flow and path.read_text() == before


def test_a_flow_the_user_already_has_is_never_replaced(tmp_path, monkeypatch):
    engine, _ = setup(tmp_path, monkeypatch, **OLD)
    engine.create("My own", {"nodes": [], "edges": []}, enabled=True, flow_id="thermostat")
    retire_thermostat(engine)
    assert engine.flows["thermostat"]["name"] == "My own" and engine.flows["thermostat"]["enabled"] is True
    assert config.INTEGRATIONS == ["zigbee"]  # the integration is still dropped


def test_nothing_to_migrate_on_a_fresh_install(tmp_path, monkeypatch):
    engine, _ = setup(tmp_path, monkeypatch, INTEGRATIONS=["zigbee"])
    retire_thermostat(engine)
    assert engine.flows == {} and config.INTEGRATIONS == ["zigbee"]


def test_only_thermostat_added_leaves_an_explicit_empty_list(tmp_path, monkeypatch):
    engine, _ = setup(tmp_path, monkeypatch, **{**OLD, "INTEGRATIONS": ["thermostat"]})
    retire_thermostat(engine)
    assert config.INTEGRATIONS == ["none"] or config.INTEGRATIONS == []
