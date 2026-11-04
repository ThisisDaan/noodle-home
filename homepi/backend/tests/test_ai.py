import json
import os
import tempfile

os.environ.setdefault("HOMEPI_DATA", tempfile.mkdtemp())
os.environ["HOMEPI_AUTOMATIONS"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from homepi import aicontext, config, main  # noqa: E402
from homepi.hub import Device, Entity  # noqa: E402

FLOW = """\
id: ai-lamp
name: Lamp at sunset
enabled: true
nodes:
  sun: {type: trigger.sun, event: sunset}
  lamp: {type: action.device, device_id: zigbee:test-lamp, key: state, inputs: ['on']}
edges:
  - {from: sun, to: lamp, in: 'on'}
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(main.flows.files, "dir", tmp_path / "config" / "flows")
    lamp = Device(id="zigbee:test-lamp", source="zigbee", name="Test lamp", model="m", manufacturer="x",
                  entities={"state": Entity("state", "light", "Light", state=True),
                            "temperature": Entity("temperature", "sensor", "Temp", unit="°C", state=21.5)})
    main.hub.devices[lamp.id] = lamp
    main.store.db.execute("DELETE FROM settings WHERE key IN ('password', 'setup_started')")
    c = TestClient(main.app)
    assert c.post("/api/auth/setup", json={"password": "correct horse"}).status_code == 200
    yield c
    main.hub.devices.pop(lamp.id, None)
    for flow_id in [f for f in main.flows.flows if f.startswith("ai-")]:
        main.flows.delete(flow_id)
    main.store.db.execute("DELETE FROM settings WHERE key IN ('password', 'setup_started')")


def test_context_has_what_an_ai_needs(client):
    ctx = client.get("/api/flow/context").json()
    assert {"instructions", "format", "engine_reference", "schema", "nodes", "devices", "areas", "flows", "examples"} <= ctx.keys()
    lamp = next(d for d in ctx["devices"] if d["id"] == "zigbee:test-lamp")
    assert {e["key"] for e in lamp["entities"]} == {"state", "temperature"}
    assert "trigger.sun" in {n["type"] for n in ctx["nodes"]} and len(ctx["examples"]) >= 2
    assert "enabled: false" in ctx["instructions"]


def test_context_as_a_prompt_to_paste(client):
    text = client.get("/api/flow/context?format=markdown").text
    assert "## Devices" in text and "`zigbee:test-lamp` Test lamp" in text and "now 21.5" in text
    assert "## Examples" in text and "```yaml" in text and text.rstrip().endswith("(describe the automation here)")


def test_validate_reports_problems_and_missing_devices(client):
    ok = client.post("/api/flow/validate", json={"yaml": FLOW}).json()
    assert ok["ok"] and ok["id"] == "ai-lamp" and ok["nodes"] == 2 and ok["warnings"] == []
    missing = client.post("/api/flow/validate", json={"yaml": FLOW.replace("test-lamp", "nope")}).json()
    assert missing["ok"] and any("no device 'zigbee:nope'" in w for w in missing["warnings"])
    wrong_key = client.post("/api/flow/validate", json={"yaml": FLOW.replace("key: state", "key: bright")}).json()
    assert any("no entity 'bright'" in w and "state" in w for w in wrong_key["warnings"])
    bad = client.post("/api/flow/validate", json={"yaml": "id: x\nname: y\nnodes:\n  a: {type: trigger.nothing}\n"}).json()
    assert not bad["ok"] and "unknown type" in bad["errors"][0]
    broken = client.post("/api/flow/validate", json={"yaml": "id: [oops"}).json()
    assert not broken["ok"] and broken["errors"]


def test_import_adds_a_flow_switched_off_whatever_the_file_says(client):
    result = client.post("/api/flow/import", json={"yaml": FLOW}).json()
    assert result["ok"] and result["replaced"] is False
    flow = main.flows.flows["ai-lamp"]
    assert flow["enabled"] is False and flow["name"] == "Lamp at sunset" and len(flow["graph"]["nodes"]) == 2
    assert (main.flows.files.dir / "ai-lamp.yaml").exists()


def test_import_will_not_overwrite_unless_asked_and_then_switches_it_off(client):
    client.post("/api/flow/import", json={"yaml": FLOW})
    main.flows.update("ai-lamp", enabled=True)
    again = client.post("/api/flow/import", json={"yaml": FLOW.replace("Lamp at sunset", "Changed")}).json()
    assert again["ok"] is False and again["exists"] is True and main.flows.flows["ai-lamp"]["name"] == "Lamp at sunset"
    assert main.flows.flows["ai-lamp"]["enabled"] is True
    replaced = client.post("/api/flow/import", json={"yaml": FLOW.replace("Lamp at sunset", "Changed"), "replace": True}).json()
    assert replaced["ok"] and replaced["replaced"] is True
    assert main.flows.flows["ai-lamp"]["name"] == "Changed" and main.flows.flows["ai-lamp"]["enabled"] is False


def test_invalid_import_changes_nothing(client):
    before = set(main.flows.flows)
    result = client.post("/api/flow/import", json={"yaml": "id: ai-bad\nname: x\nnodes: [oops]\n"}).json()
    assert result["ok"] is False and set(main.flows.flows) == before


def test_ai_endpoints_need_a_login():
    anonymous = TestClient(main.app)
    assert anonymous.get("/api/flow/context").status_code == 401
    assert anonymous.post("/api/flow/import", json={"yaml": FLOW}).status_code == 401


def test_file_problems_reach_open_pages(client, tmp_path):
    seen = []
    main.hub.broadcast = lambda message, _orig=main.hub.broadcast: (seen.append(json.loads(json.dumps(message, default=str))), _orig(message))[1]
    try:
        folder = main.flows.files.dir
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ai-broken.yaml").write_text("id: ai-broken\nname: x\nnodes:\n  a: {type: nope}\nedges: []\n")
        main.flows._watch_files()
    finally:
        del main.hub.broadcast
        main.flows.file_issues.pop("ai-broken.yaml", None)
    assert any(m.get("type") == "flow_files" and "ai-broken.yaml" in m["issues"] for m in seen)


def test_device_warnings_helper():
    flow = {"graph": {"nodes": [{"id": "n", "data": {"device_id": "zigbee:zzz", "key": "k"}}]}}
    assert aicontext.device_warnings(flow, main.hub) == ["node n: no device 'zigbee:zzz' on this hub"]


def test_home_name_is_in_the_live_snapshot_and_changes_are_pushed(client, monkeypatch):
    monkeypatch.setattr(config, "HOME_NAME", "Our house")
    with client.websocket_connect("/api/ws") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot" and snapshot["home_name"] == "Our house"
