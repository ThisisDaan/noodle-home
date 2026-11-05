import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

from noodle import config  # noqa: E402
from noodle.adapters.zigbee import ZigbeeAdapter  # noqa: E402
from noodle.hub import Hub  # noqa: E402
from noodle.store import Store  # noqa: E402


def test_the_older_homepi_variables_still_work_and_noodle_ones_win(monkeypatch):
    monkeypatch.delenv("NOODLE_PORT", raising=False)
    monkeypatch.setenv("HOMEPI_PORT", "9001")
    assert config._env("PORT", "8090") == "9001"
    monkeypatch.setenv("NOODLE_PORT", "9002")
    assert config._env("PORT", "8090") == "9002"
    monkeypatch.delenv("NOODLE_PORT")
    monkeypatch.delenv("HOMEPI_PORT")
    assert config._env("PORT", "8090") == "8090"


def test_an_existing_homepi_database_keeps_being_used(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert config.db_path() == tmp_path / "noodle.db"  # a new hub
    (tmp_path / "homepi.db").write_bytes(b"")
    assert config.db_path() == tmp_path / "homepi.db"  # an older hub
    (tmp_path / "noodle.db").write_bytes(b"")
    assert config.db_path() == tmp_path / "noodle.db"  # once it has the new one


def test_forwarded_presses_arrive_on_both_mqtt_topics(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    adapter = ZigbeeAdapter(Hub(Store(tmp_path / "db.sqlite")))
    seen = []
    adapter.on_hook = seen.append
    adapter._handle("noodle/hook/button_a", b"")
    adapter._handle("homepi/hook/button_b", b"")
    assert seen == ["button_a", "button_b"]
