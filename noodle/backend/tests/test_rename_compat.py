import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

from noodle import config  # noqa: E402
from noodle.plugins.zigbee.adapter import ZigbeeAdapter  # noqa: E402
from noodle.hub import Hub  # noqa: E402
from noodle.store import Store  # noqa: E402


def test_forwarded_presses_arrive_on_both_mqtt_topics(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    adapter = ZigbeeAdapter(Hub(Store(tmp_path / "db.sqlite")))
    seen = []
    adapter.on_hook = seen.append
    adapter._handle("noodle/hook/button_a", b"")
    adapter._handle("homepi/hook/button_b", b"")
    assert seen == ["button_a", "button_b"]
