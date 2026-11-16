"""Backups: one zip with everything a hub needs to come back (the config files and the database, history included).

A zip holds `manifest.json`, `noodle.db` and `config/...` (the files of the config folder). Backups the hub keeps
itself (nightly, and one made before every restore) live in `<data>/backups/`; a downloaded one is never kept.

A restore is staged: the zip is checked, copied to `<data>/restore-pending.zip`, and the hub restarts. On start, before
the database is opened, `apply_pending` swaps the files in. Every step can run again after a crash halfway.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
import zipfile
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from . import __version__, config
from .yamlfile import new_yaml

log = logging.getLogger(__name__)

FORMAT = 1
KEEP = {"nightly": 7, "before-restore": 3}  # how many of each kind the hub keeps
KINDS = {"nightly": "Nightly", "before-restore": "Before restore", "manual": "Download", "upload": "Uploaded"}
NIGHTLY_HOUR = 3
_NAME = re.compile(r"^noodle-backup-[0-9-]+-(?:nightly|before-restore|upload-[0-9a-f]+)\.zip$")


def backup_dir() -> Path:
    return config.DATA_DIR / "backups"


def pending_path() -> Path:
    return config.DATA_DIR / "restore-pending.zip"


class BackupError(ValueError):
    """The file is not a Noodle backup, or is damaged. The message is shown to the user."""


# --- making one ------------------------------------------------------------

def _counts(flow_names: list[str], areas_text: str | None, db_file: Path | None) -> dict:
    areas: list = []
    devices: dict = {}
    if areas_text:
        try:
            doc = new_yaml().load(areas_text) or {}
            areas, devices = list(doc.get("areas") or []), dict(doc.get("devices") or {})
        except Exception:
            pass
    history = 0
    if db_file is not None:
        try:
            with closing(sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)) as db:
                history = db.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        except sqlite3.Error:
            pass
    return {"flows": len(flow_names), "areas": len(areas), "devices": len(devices), "history": history}


def current() -> dict:
    """The same numbers for this hub as it is now, to compare with a backup before restoring."""
    flows = [p.name for p in (config.CONFIG_DIR / "flows").glob("*.yaml")]
    areas = config.CONFIG_DIR / "areas.yaml"
    db = config.db_path()
    return {"noodle": __version__,
            **_counts(flows, areas.read_text(encoding="utf-8") if areas.exists() else None, db if db.exists() else None)}


def _snapshot_db(target: Path) -> None:
    """A consistent copy of the live database, safe while the hub keeps writing."""
    source = config.db_path()
    if not source.exists():
        sqlite3.connect(target).close()
        return
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def write(target: Path, kind: str) -> Path:
    """Write a backup zip to `target`."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        db = Path(tmp) / "noodle.db"
        _snapshot_db(db)
        files = sorted(p for p in config.CONFIG_DIR.rglob("*") if p.is_file()) if config.CONFIG_DIR.exists() else []
        rel = [p.relative_to(config.CONFIG_DIR).as_posix() for p in files]
        areas = config.CONFIG_DIR / "areas.yaml"
        manifest = {"format": FORMAT, "noodle": __version__, "created": time.time(), "kind": kind,
                    **_counts([r for r in rel if _is_flow(r)], areas.read_text(encoding="utf-8") if areas.exists() else None, db)}
        partial = target.with_suffix(".part")
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.write(db, "noodle.db")
            for path, name in zip(files, rel):
                z.write(path, f"config/{name}")
        os.replace(partial, target)
    if os.name == "posix":
        os.chmod(target, 0o600)  # it holds the secrets and the password hash
    return target


def _is_flow(rel: str) -> bool:
    p = PurePosixPath(rel)
    return len(p.parts) == 2 and p.parts[0] == "flows" and p.suffix == ".yaml"


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H%M%S")


def make(kind: str) -> Path:
    """A backup the hub keeps (nightly or before a restore), then drop the oldest beyond KEEP."""
    path = write(backup_dir() / f"noodle-backup-{_stamp()}-{kind}.zip", kind)
    prune()
    return path


def make_download() -> Path:
    """A backup to download; the caller deletes it once sent."""
    fd, name = tempfile.mkstemp(prefix="noodle-download-", suffix=".zip", dir=config.DATA_DIR)
    os.close(fd)
    return write(Path(name), "manual")


def download_name() -> str:
    return f"noodle-backup-{_stamp()}.zip"


def prune() -> None:
    folder = backup_dir()
    if not folder.exists():
        return
    for kind, keep in KEEP.items():
        for old in sorted(folder.glob(f"noodle-backup-*-{kind}.zip"), reverse=True)[keep:]:
            old.unlink(missing_ok=True)
    day_ago = time.time() - 86400
    for leftover in [*folder.glob("noodle-backup-*-upload-*.zip"), *folder.glob("*.part")]:
        if leftover.stat().st_mtime < day_ago:  # an upload that was looked at but never restored
            leftover.unlink(missing_ok=True)


def next_nightly(now: datetime | None = None) -> float:
    """Seconds until the next nightly backup (03:00 local time)."""
    now = now or datetime.now()
    due = now.replace(hour=NIGHTLY_HOUR, minute=0, second=0, microsecond=0)
    if due <= now:
        due += timedelta(days=1)
    return (due - now).total_seconds()


# --- listing and checking ---------------------------------------------------

def path_of(name: str) -> Path:
    """A kept backup by its file name; never a path outside the backups folder."""
    if not _NAME.match(name) or not (backup_dir() / name).is_file():
        raise BackupError("That backup does not exist (any more).")
    return backup_dir() / name


def _manifest(z: zipfile.ZipFile) -> dict:
    try:
        manifest = json.loads(z.read("manifest.json"))
    except KeyError:
        raise BackupError("This is not a Noodle backup (it has no manifest.json).") from None
    except ValueError:
        raise BackupError("The backup's manifest.json is damaged.") from None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("format"), int):
        raise BackupError("The backup's manifest.json is damaged.")
    if manifest["format"] > FORMAT:
        raise BackupError("This backup was made by a newer Noodle. Update this hub first, then restore it.")
    return manifest


def listing() -> list[dict]:
    """The backups this hub keeps, newest first."""
    out = []
    folder = backup_dir()
    for path in sorted(folder.glob("noodle-backup-*.zip"), reverse=True) if folder.exists() else []:
        if "-upload-" in path.name:
            continue
        try:
            with zipfile.ZipFile(path) as z:
                m = _manifest(z)
        except (BackupError, zipfile.BadZipFile, OSError):
            continue
        out.append({"name": path.name, "size": path.stat().st_size, "created": m.get("created"), "kind": m.get("kind"),
                    "label": KINDS.get(m.get("kind"), m.get("kind")), "noodle": m.get("noodle"),
                    **{k: m.get(k, 0) for k in ("flows", "areas", "devices", "history")}})
    return out


def _safe_names(z: zipfile.ZipFile) -> list[str]:
    names = z.namelist()
    for name in names:
        if name == "config/":
            continue
        p = PurePosixPath(name)
        if ("\\" in name or p.is_absolute() or ".." in p.parts or ":" in name
                or not (name in ("manifest.json", "noodle.db") or (p.parts[0] == "config" and len(p.parts) > 1))):
            raise BackupError(f"The backup holds a file Noodle will not restore: {name}")
    if "noodle.db" not in names:
        raise BackupError("The backup has no database (noodle.db).")
    return names


def inspect(path: Path) -> dict:
    """Check a backup completely (as restoring would) and say what is in it."""
    try:
        with zipfile.ZipFile(path) as z:
            manifest = _manifest(z)
            names = _safe_names(z)
            if (bad := z.testzip()) is not None:
                raise BackupError(f"The backup is damaged ({bad}).")
            with tempfile.TemporaryDirectory(dir=path.parent) as tmp:
                db = Path(tmp) / "noodle.db"
                with z.open("noodle.db") as src, open(db, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                _check_db(db)
                areas = z.read("config/areas.yaml").decode("utf-8") if "config/areas.yaml" in names else None
                counts = _counts([n[7:] for n in names if n.startswith("config/") and _is_flow(n[7:])], areas, db)
    except zipfile.BadZipFile:
        raise BackupError("This file is not a zip file, or it is damaged.") from None
    newer = _version(manifest.get("noodle")) > _version(__version__)
    return {"created": manifest.get("created"), "noodle": manifest.get("noodle"), "kind": manifest.get("kind"),
            "newer": newer, **counts}


def _version(text) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", str(text or "").split("-")[0])[:3])


def _check_db(db: Path) -> None:
    try:
        with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
            ok = conn.execute("PRAGMA quick_check").fetchone()[0]
    except sqlite3.Error:
        ok = "not a database"
    if ok != "ok":
        raise BackupError("The database in the backup is damaged.")


def upload_path() -> Path:
    """Where an uploaded file goes: the backups folder (deleted after a day if it is never restored)."""
    folder = backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"noodle-backup-{_stamp()}-upload-{os.urandom(4).hex()}.zip"


# --- restoring --------------------------------------------------------------

def stage(path: Path) -> None:
    """Check the backup and mark it to be restored on the next start."""
    inspect(path)
    partial = pending_path().with_suffix(".part")
    shutil.copyfile(path, partial)
    os.replace(partial, pending_path())


def _swap(new: Path, target: Path) -> None:
    """Put `new` where `target` is. The old one is kept beside it (`.restore-old`) until the whole restore is done."""
    old = target.with_name(target.name + ".restore-old")
    if target.exists():
        # `target` exists: either nothing was swapped yet, or a finished restore left an old copy. Either way
        # `target` is complete, so it becomes the old copy.
        if old.is_dir():
            shutil.rmtree(old)
        elif old.exists():
            old.unlink()
        os.replace(target, old)
    # else: a restore stopped right after moving `target` aside; `old` holds the original, keep it.
    os.replace(new, target)


def _drop_old(target: Path) -> None:
    old = target.with_name(target.name + ".restore-old")
    if old.is_dir():
        shutil.rmtree(old, ignore_errors=True)
    elif old.exists():
        old.unlink(missing_ok=True)


def apply_pending() -> bool:
    """Restore the staged backup, if there is one. Runs at start, before anything opens the files."""
    pending = pending_path()
    if not pending.exists():
        return False
    config_dir, db = config.CONFIG_DIR, config.db_path()
    new_config = config_dir.with_name(config_dir.name + ".restore-new")
    new_db = db.with_name(db.name + ".restore-new")
    try:
        if new_config.exists():
            shutil.rmtree(new_config)
        new_db.unlink(missing_ok=True)
        with zipfile.ZipFile(pending) as z:
            _manifest(z)
            names = _safe_names(z)
            new_config.mkdir(parents=True)
            for name in names:
                if name.startswith("config/") and not name.endswith("/"):
                    out = new_config / name[7:]
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(name) as src, open(out, "wb") as dst:
                        shutil.copyfileobj(src, dst)
            with z.open("noodle.db") as src, open(new_db, "wb") as dst:
                shutil.copyfileobj(src, dst)
        _check_db(new_db)
    except (BackupError, zipfile.BadZipFile, OSError) as err:
        log.error("the staged backup could not be restored, keeping the current data: %s", err)
        shutil.rmtree(new_config, ignore_errors=True)
        new_db.unlink(missing_ok=True)
        os.replace(pending, pending.with_name("restore-failed.zip"))
        return False
    for leftover in (db.with_name(db.name + "-journal"), db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")):
        leftover.unlink(missing_ok=True)
    _swap(new_config, config_dir)
    _swap(new_db, db)
    pending.unlink()
    _drop_old(config_dir)
    _drop_old(db)
    log.info("restored the backup")
    return True
