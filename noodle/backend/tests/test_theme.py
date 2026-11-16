import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())

import pytest  # noqa: E402

from noodle import config  # noqa: E402
from noodle.yamlfile import YamlFile  # noqa: E402


@pytest.fixture
def files(tmp_path, monkeypatch):
    for _, (attr, _, _) in config.SETTINGS.items():
        monkeypatch.setattr(config, attr, getattr(config, attr))
    monkeypatch.setattr(config, "_SETTINGS", YamlFile(tmp_path / "settings.yaml"))
    monkeypatch.setattr(config, "_SECRETS", YamlFile(tmp_path / "secrets.yaml", private=True))
    return tmp_path


def test_theme_is_kept_by_name_and_read_back(files):
    config.save({"theme": "dracula"})
    assert "appearance:\n  theme: dracula\n" in (files / "settings.yaml").read_text()
    config.THEME = ""
    assert config.load() == {"theme"} and config.theme() == "dracula"


def test_no_theme_or_an_unknown_one_means_noodle(files):
    assert config.theme() == ""
    (files / "settings.yaml").write_text("appearance:\n  theme: no-such-theme\n")
    config.load()
    assert config.theme() == ""


def test_colour_map_from_a_development_version_means_noodle_and_is_replaced(files):
    """Before themes were picked from a list, a development version kept a map of colours here."""
    (files / "settings.yaml").write_text("appearance:\n  theme: {background: '#10131f', text: '#e9ebf2', primary: '#9295ff'}\n")
    config.load()
    assert config.theme() == ""
    config.load()  # reading it twice changes nothing
    assert config.theme() == ""
    config.save({"theme": "nord"})
    assert "theme: nord" in (files / "settings.yaml").read_text() and config.theme() == "nord"


def test_api_takes_only_known_themes(files):
    from fastapi.testclient import TestClient

    from noodle import main

    client = TestClient(main.app)
    main.app.dependency_overrides[main.require_login] = lambda: None
    try:
        assert client.put("/api/theme", json={"theme": "nope"}).status_code == 400
        assert client.put("/api/theme", json={"theme": "synthwave"}).json() == {"theme": "synthwave"}
        assert client.put("/api/theme", json={"theme": ""}).json() == {"theme": ""}
    finally:
        main.app.dependency_overrides.clear()
