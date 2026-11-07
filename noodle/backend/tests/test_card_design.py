import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

from noodle import main  # noqa: E402


def slot(x, y, w, h, component="value", key="k", **more):
    return {"x": x, "y": y, "w": w, "h": h, "component": component, "key": key, **more}


def test_good_designs_are_kept():
    design = {"d1": {"w": 2, "h": 1, "slots": [
        slot(0, 0, 1, 2, "switch", "heating", label=" Heat "),
        slot(1, 0, 3, 2, "dial", "target"),
        slot(4, 0, 4, 2, "value", "status", style="chip"),
        slot(4, 0, 1, 1, "value", "x", style="text-s")]}}  # covers the status: dropped
    clean = main._clean_cards(design)["d1"]
    assert clean["w"] == 2 and clean["h"] == 1
    assert clean["slots"][0] == slot(0, 0, 1, 2, "switch", "heating", label="Heat")
    assert [s["component"] for s in clean["slots"]] == ["switch", "dial", "value"]
    assert clean["slots"][2]["style"] == "chip"


def test_what_does_not_fit_is_dropped():
    design = {"d": {"w": 1, "h": 1, "slots": [
        slot(0, 0, 2, 2, key="a"),
        slot(1, 1, 1, 1, key="b"),                  # overlaps a
        slot(4, 0, 1, 1, key="c"),                  # outside a 4x2 grid
        slot(2, 0, 3, 1, key="d"),                  # sticks out
        slot(2, 0, 1, 1, "wheel", "e"),             # unknown component
        {**slot(2, 0, 1, 1, key="f"), "x": True},
        slot(2, 1, 1, 1, "switch", ""),             # no field
        slot(2, 1, 1, 1, key="g", style="neon", hours=5)]},  # unknown style and hours are just left out
        "bad": {"w": 9, "h": 1, "slots": []}, "worse": "x"}
    clean = main._clean_cards(design)
    assert set(clean) == {"d"} and [s["key"] for s in clean["d"]["slots"]] == ["a", "g"]
    assert "style" not in clean["d"]["slots"][1] and "hours" not in clean["d"]["slots"][1]


def test_first_version_designs_are_upgraded_and_stay_the_same_when_run_twice():
    old = {"d1": {"size": "wide", "slots": [{"at": 0, "component": "switch", "key": "heating", "label": "Heat"},
                                            {"at": 1, "component": "dial", "key": "target"},
                                            {"at": 3, "component": "value", "key": "status"}]},
           "d2": {"size": "large", "slots": [{"at": 0, "component": "graph", "key": "t"}, {"at": 2, "component": "switch", "key": "s"},
                                             {"at": 8, "component": "slider", "key": "u"}]}}
    once = main._clean_cards(old)
    assert once["d1"]["w"] == 2 and once["d1"]["h"] == 1
    assert [(s["x"], s["w"]) for s in once["d1"]["slots"]] == [(0, 2), (2, 4), (6, 2)]  # 4 old columns -> 8 fine ones
    assert once["d1"]["slots"][0]["label"] == "Heat"
    graph = once["d2"]["slots"][0]
    assert graph["component"] == "value" and graph["style"] == "line" and (graph["w"], graph["h"]) == (4, 2)  # 2 of 3 old rows -> 2 of 4 fine ones
    assert len(once["d2"]["slots"]) == 3  # nothing overlapped in the stretch
    assert main._clean_cards(once) == once  # a second run changes nothing


def test_a_layout_save_without_cards_keeps_the_cards(monkeypatch, tmp_path):
    from noodle.yamlfile import YamlFile
    monkeypatch.setattr(main, "dashboard", YamlFile(tmp_path / "dashboard.yaml"))
    saved = main.put_layout(main.LayoutBody(cards={"d1": {"w": 1, "h": 1, "slots": [slot(0, 0, 4, 2, key="k")]}}))
    assert saved["cards"]["d1"]["slots"][0]["key"] == "k"
    again = main.put_layout(main.LayoutBody(rooms=["Study"]))  # an older page: no cards in the save
    assert again["cards"]["d1"]["w"] == 1 and again["rooms"] == ["Study"]
    removed = main.put_layout(main.LayoutBody(cards={}))
    assert removed["cards"] == {}
