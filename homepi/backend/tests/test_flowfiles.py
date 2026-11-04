import os
import tempfile
from pathlib import Path

os.environ.setdefault("HOMEPI_DATA", tempfile.mkdtemp())
os.environ["HOMEPI_AUTOMATIONS"] = "0"

import jsonschema  # noqa: E402
import pytest  # noqa: E402

from homepi import config, flowfiles  # noqa: E402
from homepi.flows import FlowEngine  # noqa: E402
from homepi.hub import Hub  # noqa: E402
from homepi.store import Store  # noqa: E402


def dump(doc) -> str:
    import io
    out = io.StringIO()
    flowfiles._yaml().dump(doc, out)
    return out.getvalue()


def canon(graph: dict) -> dict:
    """A graph the way a file keeps it (positions are whole numbers)."""
    return {"nodes": [{**n, "position": {k: round(v) for k, v in n["position"].items()}} for n in graph["nodes"]],
            "edges": graph["edges"]}


EXAMPLES = sorted((Path(__file__).resolve().parents[2] / "examples" / "flows").glob("*.yaml"))


def test_there_are_examples():
    assert len(EXAMPLES) >= 2


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_flows_are_valid_and_round_trip_through_yaml(path):
    doc = flowfiles.parse(path.read_text(encoding="utf-8"))
    errors, warnings = flowfiles.validate(doc)
    assert errors == [] and warnings == []
    flow = flowfiles.from_doc(doc)
    assert flow["enabled"] is False  # examples never start by themselves
    again = flowfiles.from_doc(flowfiles.parse(dump(flowfiles.to_doc(flow))))
    assert canon(again["graph"]) == canon(flow["graph"]) and again["name"] == flow["name"]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_flows_match_the_json_schema(path):
    jsonschema.validate(flowfiles._plain(flowfiles.parse(path.read_text(encoding="utf-8"))), flowfiles.schema())


def test_validation_names_the_problem():
    doc = flowfiles.parse("""
id: Bad Id
name: x
nodes:
  a: {type: trigger.nothing}
  b: {type: action.timer, minutes: soon, bogus: 1}
  c: {type: action.http, url: x, method: GET}
  d: {type: action.notify, priority: loud}
edges:
  - {from: a, to: missing}
""")
    errors, warnings = flowfiles.validate(doc)
    text = "\n".join(errors)
    assert "id must be" in text
    assert "unknown type 'trigger.nothing'" in text
    assert "minutes must be a number" in text
    assert "priority must be one of" in text
    assert "'missing' is not a node" in text
    assert any("bogus" in w for w in warnings)


def test_yaml_booleans_are_not_guessed():
    doc = flowfiles.parse("id: a\nname: b\nnodes:\n  x: {type: action.device, command: off}\n")
    assert doc["nodes"]["x"]["command"] == "off"  # YAML 1.2: not the boolean false
    assert flowfiles.validate(doc)[0] == []


def test_duplicate_keys_are_an_error(tmp_path):
    path = tmp_path / "a.yaml"
    path.write_text("id: a\nid: b\nname: x\n")
    flow, errors, _ = flowfiles.FlowFiles(tmp_path).read(path)
    assert flow is None and errors


def test_files_without_layout_get_one_and_ids_are_kept(tmp_path):
    path = tmp_path / "x.yaml"
    path.write_text("""id: x
name: X
nodes:
  t: {type: trigger.manual}
  l: {type: action.log, message: hi}
edges:
  - {from: t, to: l}
""")
    flow, errors, warnings = flowfiles.FlowFiles(tmp_path).read(path)
    assert errors == [] and warnings == [] and flow["enabled"] is False
    pos = {n["id"]: n["position"] for n in flow["graph"]["nodes"]}
    assert pos["t"]["x"] < pos["l"]["x"]
    assert flow["graph"]["edges"][0]["id"] == "t-out-l"


def test_saving_keeps_comments(tmp_path):
    files = flowfiles.FlowFiles(tmp_path)
    flow = {"id": "c", "name": "C", "enabled": False, "graph": {
        "nodes": [{"id": "t", "type": "trigger.manual", "position": {"x": 0, "y": 0}, "data": {}},
                  {"id": "l", "type": "action.log", "position": {"x": 360, "y": 0}, "data": {"message": "hi"}}],
        "edges": [{"id": "t-out-l", "source": "t", "sourceHandle": "out", "target": "l"}]}}
    path = files.write(flow)
    path.write_text("# my note\n" + path.read_text().replace("  l:", "  # says hi\n  l:"))
    flow["graph"]["nodes"][1]["data"]["message"] = "bye"
    flow["enabled"] = True
    files.write(flow)
    text = path.read_text()
    assert "# my note" in text and "# says hi" in text and "bye" in text and "enabled: true" in text


def engine(tmp_path, monkeypatch) -> FlowEngine:
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    store = Store(tmp_path / "db.sqlite")
    return FlowEngine(Hub(store), store)


def test_database_flows_are_exported_once_and_read_back(tmp_path, monkeypatch):
    first = engine(tmp_path, monkeypatch)
    graph = {"nodes": [{"id": "t", "type": "trigger.manual", "position": {"x": 0, "y": 0}, "data": {}}], "edges": []}
    first.create("Mine", graph, enabled=True, flow_id="mine")
    assert (tmp_path / "config" / "flows" / "mine.yaml").exists()
    again = engine(tmp_path, monkeypatch)  # a restart
    assert again.flows["mine"]["enabled"] is True and again.flows["mine"]["name"] == "Mine"


def test_file_changes_are_picked_up_and_new_flows_start_off(tmp_path, monkeypatch):
    e = engine(tmp_path, monkeypatch)
    folder = tmp_path / "config" / "flows"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ai.yaml").write_text("id: ai\nname: From AI\nenabled: true\nnodes:\n  t: {type: trigger.manual}\nedges: []\n")
    e._watch_files()
    assert e.flows["ai"]["name"] == "From AI" and e.flows["ai"]["enabled"] is False
    assert "enabled: false" in (folder / "ai.yaml").read_text()  # the file now says what is true

    (folder / "ai.yaml").write_text("id: ai\nname: Renamed\nenabled: false\nnodes:\n  t: {type: trigger.manual}\n"
                                    "  l: {type: action.log, message: hi}\nedges:\n  - {from: t, to: l}\n")
    e._watch_files()
    assert e.flows["ai"]["name"] == "Renamed" and len(e.flows["ai"]["graph"]["nodes"]) == 2

    (folder / "ai.yaml").write_text("id: ai\nname: Broken\nnodes:\n  t: {type: nope}\nedges: []\n")
    e._watch_files()
    assert e.flows["ai"]["name"] == "Renamed"  # the last good version stays
    assert e.file_issues["ai.yaml"]["errors"] and "nope" in e.file_issues["ai.yaml"]["errors"][0]

    (folder / "ai.yaml").unlink()
    e._watch_files()
    assert "ai" in e.flows  # editors replace files: one more look before deleting
    e._watch_files()
    assert "ai" not in e.flows


def test_editing_in_the_app_writes_the_file(tmp_path, monkeypatch):
    e = engine(tmp_path, monkeypatch)
    graph = {"nodes": [{"id": "t", "type": "trigger.manual", "position": {"x": 0, "y": 0}, "data": {}}], "edges": []}
    e.create("A", graph, flow_id="a")
    e.update("a", name="B", enabled=True)
    text = (tmp_path / "config" / "flows" / "a.yaml").read_text()
    assert "name: B" in text and "enabled: true" in text
    e._watch_files()  # its own write is not a change
    assert e.flows["a"]["name"] == "B"
    e.delete("a")
    assert not (tmp_path / "config" / "flows" / "a.yaml").exists()


def test_cli_validate_and_schema(tmp_path, capsys):
    (tmp_path / "ok.yaml").write_text("id: ok\nname: Ok\nnodes:\n  t: {type: trigger.manual}\nedges: []\n")
    assert flowfiles.cli(["validate", str(tmp_path)], tmp_path) == 0
    (tmp_path / "bad.yaml").write_text("id: bad\nname: Bad\nnodes:\n  t: {type: trigger.nope}\nedges: []\n")
    assert flowfiles.cli(["validate", str(tmp_path)], tmp_path) == 1
    assert "unknown type" in capsys.readouterr().err
    assert flowfiles.cli(["schema"], tmp_path) == 0
