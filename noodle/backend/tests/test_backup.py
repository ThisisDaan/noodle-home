import os
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())

import pytest  # noqa: E402

from noodle import backup, config  # noqa: E402


@pytest.fixture
def hub(tmp_path, monkeypatch):
    """A data folder with a config folder (one flow, rooms) and a database with some history."""
    data = tmp_path / "data"
    cfg = data / "config"
    (cfg / "flows").mkdir(parents=True)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "CONFIG_DIR", cfg)
    (cfg / "flows" / "porch.yaml").write_bytes(b"# my comment\nname: Porch light\n")
    (cfg / "areas.yaml").write_text("areas: [Kitchen, Hall]\ndevices:\n  dev-1: {name: Lamp, area: Hall}\n", encoding="utf-8")
    (cfg / "secrets.yaml").write_text("ha_token: placeholder\n", encoding="utf-8")
    _db(data / "noodle.db", rows=3, marker="original")
    return data


def _db(path, rows, marker):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, ts REAL, device_id TEXT, key TEXT, value TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.executemany("INSERT INTO history (ts, device_id, key, value) VALUES (0, 'dev-1', 'on', ?)", [(marker,)] * rows)
    db.execute("INSERT OR REPLACE INTO settings VALUES ('marker', ?)", (marker,))
    db.commit()
    db.close()


def _marker(data):
    with closing(sqlite3.connect(data / "noodle.db")) as db:
        return db.execute("SELECT value FROM settings WHERE key = 'marker'").fetchone()[0]


def test_backup_holds_config_and_database(hub):
    path = backup.make("nightly")
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        assert {"manifest.json", "noodle.db", "config/flows/porch.yaml", "config/areas.yaml", "config/secrets.yaml"} <= names
        assert z.read("config/flows/porch.yaml").decode() == "# my comment\nname: Porch light\n"  # byte for byte
    info = backup.inspect(path)
    assert (info["flows"], info["areas"], info["devices"], info["history"]) == (1, 2, 1, 3)
    assert backup.listing()[0]["name"] == path.name


def test_restore_replaces_everything_and_runs_twice(hub):
    path = backup.make("nightly")
    # Things change after the backup: a new flow, other rooms, other database.
    (config.CONFIG_DIR / "flows" / "new.yaml").write_text("name: New\n", encoding="utf-8")
    (config.CONFIG_DIR / "areas.yaml").write_text("areas: [Attic]\n", encoding="utf-8")
    (hub / "noodle.db").unlink()
    _db(hub / "noodle.db", rows=1, marker="later")

    backup.stage(path)
    assert backup.apply_pending()
    assert _marker(hub) == "original"
    assert not (config.CONFIG_DIR / "flows" / "new.yaml").exists()
    assert "Kitchen" in (config.CONFIG_DIR / "areas.yaml").read_text()
    assert not backup.pending_path().exists()
    assert not list(hub.glob("*.restore-*"))
    assert not backup.apply_pending()  # nothing staged: nothing happens


def test_restore_finishes_after_a_crash_halfway(hub):
    path = backup.make("nightly")
    _db(hub / "noodle.db", rows=0, marker="later")
    backup.stage(path)
    # Crash right after the config folder was moved aside, before the new one was put in.
    os.replace(config.CONFIG_DIR, config.CONFIG_DIR.with_name("config.restore-old"))
    assert backup.apply_pending()
    assert (config.CONFIG_DIR / "flows" / "porch.yaml").exists()
    assert _marker(hub) == "original"
    assert not list(hub.glob("*.restore-*"))


def test_old_database_shape_restores(hub):
    """A backup from an older hub whose database has no history table yet is still accepted."""
    old = hub / "old.zip"
    legacy = hub / "legacy.db"
    with closing(sqlite3.connect(legacy)) as db:
        db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO settings VALUES ('marker', 'legacy')")
        db.commit()
    with zipfile.ZipFile(old, "w") as z:
        z.writestr("manifest.json", '{"format": 1, "noodle": "0.1.0"}')
        z.write(legacy, "noodle.db")
        z.writestr("config/", "")
        z.writestr("config/areas.yaml", "areas: [Den]\n")
    assert backup.inspect(old)["history"] == 0
    backup.stage(old)
    assert backup.apply_pending()
    assert _marker(hub) == "legacy"


@pytest.mark.parametrize("name", ["../evil.txt", "/etc/passwd", "config/../../evil", "other.txt", "C:/x"])
def test_refuses_files_outside_the_backup(hub, name):
    bad = hub / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", '{"format": 1}')
        z.writestr("noodle.db", "")
        z.writestr(name, "x")
    with pytest.raises(backup.BackupError):
        backup.inspect(bad)


def test_refuses_what_is_not_a_backup(hub):
    junk = hub / "junk.zip"
    junk.write_bytes(b"not a zip")
    with pytest.raises(backup.BackupError):
        backup.inspect(junk)
    with zipfile.ZipFile(junk, "w") as z:
        z.writestr("manifest.json", '{"format": 1}')
        z.writestr("noodle.db", "not a database")
    with pytest.raises(backup.BackupError, match="damaged"):
        backup.inspect(junk)
    with zipfile.ZipFile(junk, "w") as z:
        z.writestr("manifest.json", '{"format": 99}')
        z.writestr("noodle.db", "")
    with pytest.raises(backup.BackupError, match="newer"):
        backup.inspect(junk)


def test_a_broken_staged_restore_keeps_the_current_data(hub):
    backup.pending_path().write_bytes(b"not a zip")
    assert not backup.apply_pending()
    assert _marker(hub) == "original"
    assert (hub / "restore-failed.zip").exists()


def test_keeps_the_last_seven_nightly(hub, monkeypatch):
    stamps = iter(f"2026-01-{d:02d}-030000" for d in range(1, 11))
    monkeypatch.setattr(backup, "_stamp", lambda: next(stamps))
    for _ in range(10):
        backup.make("nightly")
    kept = sorted(p.name for p in backup.backup_dir().glob("*.zip"))
    assert len(kept) == 7 and kept[0].startswith("noodle-backup-2026-01-04")


def test_kept_backups_only_by_their_own_name(hub):
    backup.make("nightly")
    for name in ["../noodle.db", "noodle.db", "noodle-backup-x/../../noodle.db"]:
        with pytest.raises(backup.BackupError):
            backup.path_of(name)


def test_next_nightly_is_three_oclock():
    assert backup.next_nightly(datetime(2026, 1, 1, 2, 0)) == 3600
    assert backup.next_nightly(datetime(2026, 1, 1, 3, 0)) == 24 * 3600
