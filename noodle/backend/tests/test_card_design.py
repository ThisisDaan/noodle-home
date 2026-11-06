import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

from noodle import main  # noqa: E402


def test_good_designs_are_kept():
    design = {"d1": {"size": "wide", "slots": [{"at": 0, "component": "switch", "key": "heating", "label": " Heat "},
                                              {"at": 1, "component": "dial", "key": "target"},
                                              {"at": 3, "component": "value", "key": "status"}]}}
    clean = main._clean_cards(design)
    assert clean["d1"]["slots"][0] == {"at": 0, "component": "switch", "key": "heating", "label": "Heat"}
    assert [s["component"] for s in clean["d1"]["slots"]] == ["switch", "dial", "value"]


def test_what_does_not_fit_is_dropped():
    design = {"d": {"size": "small", "slots": [
        {"at": 0, "component": "dial", "key": "a"},      # takes both slots
        {"at": 1, "component": "switch", "key": "b"},    # overlaps the dial
        {"at": 2, "component": "switch", "key": "c"},    # outside a 2x1 card
        {"at": 1, "component": "dial", "key": "d"},      # a dial would stick out
        {"at": 0, "component": "wheel", "key": "e"},     # unknown component
        {"at": True, "component": "switch", "key": "f"},
        {"at": 0, "component": "switch"}]},              # no field
        "bad": {"size": "huge", "slots": []}, "worse": "x"}
    clean = main._clean_cards(design)
    assert set(clean) == {"d"} and [s["key"] for s in clean["d"]["slots"]] == ["a"]
    graph = {"g": {"size": "large", "slots": [{"at": 0, "component": "graph", "key": "t"}, {"at": 2, "component": "switch", "key": "s"},
                                              {"at": 3, "component": "switch", "key": "u"}, {"at": 4, "component": "switch", "key": "w"}]}}
    kept = main._clean_cards(graph)["g"]["slots"]
    # the graph fills slots 0, 1, 4 and 5 (2x2): slot 4 is taken, slots 2 and 3 are free
    assert [s["key"] for s in kept] == ["t", "s", "u"]


def test_a_layout_save_without_cards_keeps_the_cards(monkeypatch, tmp_path):
    from noodle.yamlfile import YamlFile
    monkeypatch.setattr(main, "dashboard", YamlFile(tmp_path / "dashboard.yaml"))
    saved = main.put_layout(main.LayoutBody(cards={"d1": {"size": "small", "slots": [{"at": 0, "component": "value", "key": "k"}]}}))
    assert saved["cards"]["d1"]["slots"][0]["key"] == "k"
    again = main.put_layout(main.LayoutBody(rooms=["Study"]))  # an older page: no cards in the save
    assert again["cards"]["d1"]["size"] == "small" and again["rooms"] == ["Study"]
    removed = main.put_layout(main.LayoutBody(cards={}))
    assert removed["cards"] == {}
