import asyncio
import json
import os
import sqlite3
import tempfile

os.environ.setdefault("HOMEPI_DATA", tempfile.mkdtemp())
os.environ["HOMEPI_AUTOMATIONS"] = "0"

import pytest  # noqa: E402

from homepi import config, plugins  # noqa: E402
from homepi.store import Store  # noqa: E402
from homepi.yamlfile import YamlFile  # noqa: E402


@pytest.fixture
def files(tmp_path, monkeypatch):
    """settings.yaml and secrets.yaml in a temporary folder; the settings go back afterwards."""
    for _, (attr, _, _) in config.SETTINGS.items():
        monkeypatch.setattr(config, attr, getattr(config, attr))
    monkeypatch.setattr(config, "_SETTINGS", YamlFile(tmp_path / "settings.yaml"))
    monkeypatch.setattr(config, "_SECRETS", YamlFile(tmp_path / "secrets.yaml", private=True))
    monkeypatch.setattr(config, "_OLD_FILE", tmp_path / "settings.json")
    return tmp_path


def test_settings_sections_follow_the_plugins():
    for plugin in plugins.discover():
        for field in plugin.fields:
            assert config.SETTINGS[field.key][2] == plugin.id, field.key
            assert (field.key in config.SECRET_KEYS) == field.secret, field.key
        for key in plugin.forget:
            assert config.SETTINGS[key][2] == plugin.id, key


def test_settings_are_saved_per_integration_and_secrets_apart(files):
    config.save({"mqtt_host": "broker", "mqtt_port": "1884", "hue_host": "10.0.0.2", "hue_key": "s3cret",
                 "ble_sensors": "AA:BB:CC:DD:EE:FF=Kitchen", "integrations": "zigbee,hue"})
    settings = (files / "settings.yaml").read_text()
    assert "zigbee:" in settings and "mqtt_port: 1884" in settings and "hue_host: 10.0.0.2" in settings
    assert "s3cret" not in settings and "Kitchen" in settings
    assert "hue_key: s3cret" in (files / "secrets.yaml").read_text()
    assert config.MQTT_PORT == 1884 and config.INTEGRATIONS == ["zigbee", "hue"]


def test_bad_value_writes_nothing(files):
    with pytest.raises(ValueError):
        config.save({"mqtt_port": "many"})
    assert not (files / "settings.yaml").exists()


def test_hand_edits_are_found_and_removed_keys_go_back_to_default(files):
    config.save({"mqtt_host": "broker", "mqtt_port": "1884"})
    assert not config.files_changed()  # its own write is not a change
    text = (files / "settings.yaml").read_text()
    (files / "settings.yaml").write_text("# my broker\n" + text.replace("broker", "other-broker"))
    assert config.files_changed()
    assert config.load() == {"mqtt_host"} and config.MQTT_HOST == "other-broker"
    (files / "settings.yaml").write_text("zigbee:\n  mqtt_host: other-broker\n")
    assert config.load() == {"mqtt_port"} and config.MQTT_PORT == config._DEFAULTS["MQTT_PORT"]


def test_comments_survive_saving(files):
    config.save({"mqtt_host": "broker"})
    path = files / "settings.yaml"
    path.write_text("# my settings\n" + path.read_text())
    config.save({"mqtt_port": "1885"})
    assert "# my settings" in path.read_text() and "mqtt_port: 1885" in path.read_text()


def test_invalid_yaml_keeps_the_running_settings(files):
    config.save({"mqtt_host": "broker"})
    (files / "settings.yaml").write_text("zigbee: [oops\n")
    assert config.load() == set() and config.MQTT_HOST == "broker"


def test_old_settings_json_is_moved(files):
    (files / "settings.json").write_text(json.dumps({"mqtt_host": "legacy", "hue_key": "k", "mqtt_port": "1999"}))
    config._migrate_json()
    assert not (files / "settings.json").exists() and (files / "settings.json.migrated").exists()
    assert config.load() >= {"mqtt_host"} and config.MQTT_HOST == "legacy" and config.MQTT_PORT == 1999
    assert config.HUE_KEY == "k" and "hue_key" in (files / "secrets.yaml").read_text()


# --- rooms and device names ------------------------------------------------------------------------

def store(tmp_path, monkeypatch) -> Store:
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    return Store(tmp_path / "db.sqlite")


def test_rooms_start_with_the_defaults_and_live_in_a_file(tmp_path, monkeypatch):
    s = store(tmp_path, monkeypatch)
    assert s.areas() == config.DEFAULT_AREAS
    s.add_area("Attic")
    s.set_device_meta("zigbee:1", "Lamp", "Attic")
    again = store(tmp_path, monkeypatch)
    assert "Attic" in again.areas() and again.device_meta("zigbee:1") == {"name": "Lamp", "area": "Attic"}
    again.remove_area("Attic")
    assert again.device_meta("zigbee:1")["area"] is None
    assert "Attic" not in (tmp_path / "config" / "areas.yaml").read_text()


def test_rooms_move_over_from_the_database_once(tmp_path, monkeypatch):
    db = sqlite3.connect(tmp_path / "db.sqlite")
    db.executescript("CREATE TABLE areas (name TEXT PRIMARY KEY, position INTEGER NOT NULL DEFAULT 0);"
                     "CREATE TABLE device_meta (device_id TEXT PRIMARY KEY, name TEXT, area TEXT);"
                     "INSERT INTO areas VALUES ('Study', 0), ('Shed', 1);"
                     "INSERT INTO device_meta VALUES ('matter:4', 'Blanket', 'Study');")
    db.commit()
    db.close()
    s = store(tmp_path, monkeypatch)
    assert s.areas() == ["Study", "Shed"] and s.device_meta("matter:4") == {"name": "Blanket", "area": "Study"}
    assert "Blanket" in (tmp_path / "config" / "areas.yaml").read_text()


def test_hand_edited_rooms_are_picked_up_and_held_back_writes_are_flushed(tmp_path, monkeypatch):
    s = store(tmp_path, monkeypatch)
    s.set_device_meta("zigbee:2", None, "Kitchen", defer=True)
    assert "zigbee:2" not in (tmp_path / "config" / "areas.yaml").read_text()
    s.flush()
    assert "zigbee:2" in (tmp_path / "config" / "areas.yaml").read_text()
    assert not s.reload_areas()  # its own write
    path = tmp_path / "config" / "areas.yaml"
    path.write_text(path.read_text().replace("Kitchen", "Cucina"))
    assert s.reload_areas() and "Cucina" in s.areas()
    path.write_text("areas: [oops\n")
    assert not s.reload_areas()
    s.add_area("X")  # does not overwrite the file someone is fixing
    assert path.read_text() == "areas: [oops\n"


# --- dashboard and reacting to edits ---------------------------------------------------------------

def test_dashboard_layout_is_a_file(tmp_path, monkeypatch):
    from homepi import main
    monkeypatch.setattr(main, "dashboard", YamlFile(tmp_path / "dashboard.yaml"))
    assert main.get_layout() == {"rooms": [], "hidden": [], "favorites": [], "order": [], "widgets": None,
                                 "devices_view": {"group_by": "room", "sort": "name"}}
    main.put_layout(main.LayoutBody(rooms=["Kitchen", "Hall"], favorites=["zigbee:1"]))
    assert "rooms: [Kitchen, Hall]" in (tmp_path / "dashboard.yaml").read_text()
    assert not main.dashboard.changed()
    (tmp_path / "dashboard.yaml").write_text("rooms: [Hall]\nhidden: [zigbee:9]\n")
    assert main.dashboard.changed()
    assert main._read_layout() == {"rooms": ["Hall"], "hidden": ["zigbee:9"], "favorites": [], "order": [], "widgets": None,
                                   "devices_view": {"group_by": "room", "sort": "name"}}


def test_changed_settings_restart_only_their_integration(monkeypatch):
    from homepi import main
    restarted = []

    async def fake_restart(source):
        restarted.append(source)

    monkeypatch.setattr(main, "restart_adapter", fake_restart)
    monkeypatch.setattr(config, "INTEGRATIONS", ["zigbee", "matter", "hue"])
    monkeypatch.setattr(main, "tasks", {"zigbee": _Running(), "matter": _Running(), "hue": _Running()})
    asyncio.run(main._apply_settings({"hue_host"}))
    assert restarted == ["hue"]
    restarted.clear()
    asyncio.run(main._apply_settings({"mqtt_host", "ntfy_topic"}))
    assert restarted == ["zigbee"]


class _Running:
    def done(self):
        return False

    def cancel(self):
        pass


# --- the thermostat is no longer tied to one install's devices ---------------------------------------

def test_fresh_install_has_no_thermostat(tmp_path, monkeypatch):
    from homepi.hub import Hub
    from homepi.plugins.thermostat import PLUGIN

    s = store(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "BLE_SENSORS", {})
    assert config.THERMOSTAT_SENSOR_DEVICE == "" and not PLUGIN.preset()
    adapter = PLUGIN.create_adapter(Hub(s))
    assert adapter.configured is False and PLUGIN.status(adapter) is None
    asyncio.run(adapter.run())  # returns at once, publishes nothing
    assert adapter.hub.devices == {}


def test_thermostat_follows_the_settings_and_can_be_removed(tmp_path, monkeypatch):
    from homepi.hub import Hub
    from homepi.plugins.thermostat import PLUGIN

    s = store(tmp_path, monkeypatch)
    for attr, value in (("THERMOSTAT_SENSOR_DEVICE", "ble:1"), ("THERMOSTAT_SENSOR_KEY", "temperature"),
                        ("THERMOSTAT_HEATER_DEVICE", "zigbee:2"), ("THERMOSTAT_HEATER_KEY", "switch"),
                        ("THERMOSTAT_NAME", "Study heating"), ("THERMOSTAT_ID", "thermostat:study")):
        monkeypatch.setattr(config, attr, value)
    hub = Hub(s)
    adapter = PLUGIN.create_adapter(hub)
    adapter._publish()
    assert hub.devices["thermostat:study"].name == "Study heating"
    PLUGIN.on_remove(hub, adapter)
    assert "thermostat:study" not in hub.devices


# --- where the home is, and its time zone --------------------------------------------------------------

def test_location_and_timezone_are_settings(files, monkeypatch):
    monkeypatch.setattr(config, "LOCATION_SET", False)
    monkeypatch.setitem(os.environ, "TZ", os.environ.get("TZ", "UTC"))  # put back afterwards
    config.save({"latitude": "40.7128", "longitude": "-74.006", "timezone": "America/New_York"})
    assert (config.LATITUDE, config.LONGITUDE, config.TIMEZONE) == (40.7128, -74.006, "America/New_York")
    assert config.LOCATION_SET is True and os.environ["TZ"] == "America/New_York"
    text = (files / "settings.yaml").read_text()
    assert "system:" in text and "latitude: 40.7128" in text and "timezone: America/New_York" in text
    config.save({"timezone": ""})
    assert os.environ.get("TZ") != "America/New_York"


@pytest.mark.parametrize("values", [{"latitude": "91"}, {"longitude": "-181"}, {"latitude": "north"},
                                    {"timezone": "Mars/Olympus"}])
def test_bad_location_is_refused_and_nothing_changes(files, values):
    before = (config.LATITUDE, config.LONGITUDE, config.TIMEZONE)
    with pytest.raises(ValueError):
        config.save(values)
    assert (config.LATITUDE, config.LONGITUDE, config.TIMEZONE) == before and not (files / "settings.yaml").exists()


def test_location_set_follows_the_file(files, monkeypatch):
    monkeypatch.setattr(config, "LOCATION_SET", False)
    config.save({"latitude": "10", "longitude": "20"})
    (files / "settings.yaml").write_text("system:\n  public_url: http://hub\n")
    config.load()
    assert config.LOCATION_SET is False and config.LATITUDE == config._DEFAULTS["LATITUDE"]


def test_sun_times_follow_the_location(files, monkeypatch):
    from datetime import date

    from homepi import sun
    monkeypatch.setattr(config, "LOCATION_SET", False)
    config.save({"latitude": "52.37", "longitude": "4.9"})
    amsterdam = sun.times(date(2026, 6, 21))
    config.save({"latitude": "-33.87", "longitude": "151.2"})  # Sydney: winter in June
    sydney = sun.times(date(2026, 6, 21))
    assert amsterdam != sydney and (amsterdam[1] - amsterdam[0]) > (sydney[1] - sydney[0])


def test_hub_settings_report_location_state():
    from homepi.plugins.hub_settings import PLUGIN
    info = PLUGIN.details(None)
    assert set(info) == {"location_set", "timezone_now", "time_now"}


# --- first-run wizard ------------------------------------------------------------------------------

def test_wizard_shows_for_a_new_hub_until_finished(files, monkeypatch):
    from fastapi.testclient import TestClient

    from homepi import main
    monkeypatch.setattr(config, "SETUP_DONE", False)
    main.store.db.execute("DELETE FROM settings WHERE key IN ('password', 'setup_started')")
    try:
        client = TestClient(main.app)
        assert client.get("/api/auth/status").json() == {"setup_needed": True, "logged_in": False, "wizard": False}
        assert client.post("/api/auth/setup", json={"password": "correct horse"}).status_code == 200
        assert client.get("/api/auth/status").json()["wizard"] is True
        main._mark_existing_install_done()  # a restart in the middle of the wizard
        assert client.get("/api/auth/status").json()["wizard"] is True
        assert client.post("/api/setup/finish").json() == {"ok": True}
        assert client.get("/api/auth/status").json()["wizard"] is False
        assert "setup_done: true" in (files / "settings.yaml").read_text()
        assert TestClient(main.app).get("/api/auth/status").json()["wizard"] is False  # not logged in
    finally:
        main.store.db.execute("DELETE FROM settings WHERE key IN ('password', 'setup_started')")


def test_a_hub_from_before_the_wizard_is_marked_done(files, monkeypatch):
    from homepi import main
    monkeypatch.setattr(config, "SETUP_DONE", False)
    main.store.db.execute("DELETE FROM settings WHERE key = 'setup_started'")
    monkeypatch.setattr(main.store, "has_password", lambda: True)
    main._mark_existing_install_done()
    assert config.SETUP_DONE is True


def test_finishing_needs_a_login(files):
    from fastapi.testclient import TestClient

    from homepi import main
    assert TestClient(main.app).post("/api/setup/finish").status_code == 401


def test_home_name_is_a_hub_setting(files):
    config.save({"home_name": "Our house"})
    assert config.HOME_NAME == "Our house" and "home_name: Our house" in (files / "settings.yaml").read_text()


def test_new_hub_starts_with_nothing_added_and_keeps_that_after_the_wizard(files, monkeypatch):
    from fastapi.testclient import TestClient

    from homepi import integrations, main
    monkeypatch.setattr(config, "SETUP_DONE", False)
    monkeypatch.setattr(config, "INTEGRATIONS", [])
    main.store.db.execute("DELETE FROM settings WHERE key IN ('password', 'setup_started')")
    try:
        client = TestClient(main.app)
        client.post("/api/auth/setup", json={"password": "correct horse"})
        assert integrations.added_ids() == []  # not zigbee and matter by default
        client.post("/api/setup/finish")
        assert config.SETUP_DONE and integrations.added_ids() == ["none"]  # stays empty, not "whatever is set up"
    finally:
        main.store.db.execute("DELETE FROM settings WHERE key IN ('password', 'setup_started')")


def test_dashboard_widgets_and_device_view_are_saved_cleaned_and_editable_by_hand(tmp_path, monkeypatch):
    from homepi import main
    monkeypatch.setattr(main, "dashboard", YamlFile(tmp_path / "dashboard.yaml"))
    saved = main.put_layout(main.LayoutBody(
        widgets=[{"type": "favourites"}, {"type": "sensor", "device_id": "ble:1", "key": "temperature", "hours": 9999,
                                          "evil": "x"}, {"type": "nonsense"}, {"type": "flows", "title": "Quick"}],
        devices_view={"group_by": "type", "sort": "recent"}))
    assert saved["widgets"] == [{"type": "favourites"},
                                {"type": "sensor", "device_id": "ble:1", "key": "temperature", "hours": 336},
                                {"type": "flows", "title": "Quick"}]
    assert saved["devices_view"] == {"group_by": "type", "sort": "recent"}
    text = (tmp_path / "dashboard.yaml").read_text()
    assert "widgets:" in text and "type: favourites" in text and "group_by: type" in text
    (tmp_path / "dashboard.yaml").write_text("widgets:" + chr(10) + "  - {type: rooms}" + chr(10) + "  - {type: bogus}" + chr(10) + "devices_view: {group_by: weird}" + chr(10))
    assert main._read_layout()["widgets"] == [{"type": "rooms"}]
    assert main._read_layout()["devices_view"] == {"group_by": "room", "sort": "name"}
    main.put_layout(main.LayoutBody(widgets=[]))
    assert main._read_layout()["widgets"] == []  # an empty list is a choice: no cards


def test_a_fresh_database_has_no_legacy_tables_but_an_old_one_is_still_read(tmp_path, monkeypatch):
    s = store(tmp_path, monkeypatch)
    tables = {r[0] for r in s.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not {"areas", "device_meta", "automations"} & tables
    assert s.areas() == config.DEFAULT_AREAS  # defaults, without touching the missing tables


def test_forwarded_hue_buttons_come_from_a_file(tmp_path, monkeypatch):
    from homepi.adapters import hue

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    assert hue.legacy_switches() == {} and hue.legacy_buttons() == {}
    (tmp_path / "hue-hooks.yaml").write_text("hue:tap:" + chr(10) + "  name: Tap" + chr(10) + "  model: Hue Tap" + chr(10) + "  buttons:" + chr(10) + "    tap_1: [button_1, Button 1]" + chr(10))
    assert hue.legacy_buttons() == {"tap_1": ("hue:tap", "button_1")}
    assert hue.legacy_switches()["hue:tap"][0] == "Tap"
    (tmp_path / "hue-hooks.yaml").write_text("hue:tap: [broken" + chr(10))
    assert hue.legacy_buttons() == {}  # a broken file does not break the hub
