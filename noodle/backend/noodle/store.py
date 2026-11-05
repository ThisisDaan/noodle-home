"""SQLite storage for runtime state (history, timers, login). The rooms and the names and rooms of devices
live in config/areas.yaml, where they can be edited by hand."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from . import config
from .yamlfile import YamlFile

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- Since when an entity has had its current state; survives restarts, so
-- "on for 2 hours" rules keep counting.
CREATE TABLE IF NOT EXISTS entity_since (
    device_id TEXT NOT NULL,
    key TEXT NOT NULL,
    state TEXT NOT NULL,
    since REAL NOT NULL,
    PRIMARY KEY (device_id, key)
);
-- Minutes a motion sensor keeps reporting "presence" after the last motion.
CREATE TABLE IF NOT EXISTS presence_minutes (device_id TEXT PRIMARY KEY, minutes REAL NOT NULL);
CREATE TABLE IF NOT EXISTS variables (name TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL NOT NULL);
-- Every state change and button press of every device; how long it is kept is the history_days setting.
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    device_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_device ON history (device_id, ts);
"""


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._pruned = 0.0
        self.db.executescript(SCHEMA)
        self.db.commit()
        self._areas_file = YamlFile(config.CONFIG_DIR / "areas.yaml")
        self._lock = threading.RLock()
        self._areas: list[str] = []
        self._meta: dict[str, dict] = {}  # device id -> {"name": ..., "area": ...}
        self._dirty = False
        self._broken = False  # the file could not be read: leave it alone until it can
        self._load_areas()

    # settings
    def get(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        self.db.commit()

    def session_secret(self) -> str:
        secret = self.get("session_secret")
        if not secret:
            secret = secrets.token_hex(32)
            self.set("session_secret", secret)
        return secret

    # password (PBKDF2, stored as salt$hash)
    def has_password(self) -> bool:
        return self.get("password") is not None

    def set_password(self, password: str) -> None:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
        self.set("password", f"{salt}${digest}")

    def check_password(self, password: str) -> bool:
        stored = self.get("password")
        if not stored:
            return False
        salt, digest = stored.split("$", 1)
        attempt = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
        return hmac.compare_digest(attempt, digest)

    # app tokens (the Noodle Android app): only a hash is kept, so a leaked database cannot be used to log in
    def add_app_token(self, name: str, kind: str = "app") -> str:
        token = secrets.token_urlsafe(32)
        tokens = json.loads(self.get("app_tokens") or "{}")
        tokens[hashlib.sha256(token.encode()).hexdigest()] = {"name": name, "created": time.time(), "kind": kind}
        self.set("app_tokens", json.dumps(tokens))
        return token

    def app_tokens(self, kind: str) -> list[dict]:
        """The tokens of one kind (never the token itself): {id, name, created}."""
        tokens = json.loads(self.get("app_tokens") or "{}")
        return sorted(({"id": h[:16], "name": t.get("name", ""), "created": t.get("created", 0)}
                       for h, t in tokens.items() if t.get("kind") == kind), key=lambda t: t["created"])

    def remove_app_token(self, token_id: str, kind: str) -> bool:
        tokens = json.loads(self.get("app_tokens") or "{}")
        hit = [h for h, t in tokens.items() if h[:16] == token_id and t.get("kind") == kind]
        for h in hit:
            del tokens[h]
        if hit:
            self.set("app_tokens", json.dumps(tokens))
        return bool(hit)

    def check_app_token(self, token: str) -> bool:
        return hashlib.sha256(token.encode()).hexdigest() in json.loads(self.get("app_tokens") or "{}")

    # rooms and device names (config/areas.yaml)
    def _load_areas(self) -> None:
        if self._areas_file.exists():
            try:
                self._take(self._areas_file.read())
                return
            except ValueError as err:
                log.warning("%s (using the last saved rooms until it is fixed)", err)
                self._broken = True
        # First start with files: bring over what an older database held (its tables are not created any more).
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self._areas = ([r["name"] for r in self.db.execute("SELECT name FROM areas ORDER BY position, name")]
                       if "areas" in tables else []) or list(config.DEFAULT_AREAS)
        self._meta = ({r["device_id"]: {"name": r["name"], "area": r["area"]}
                       for r in self.db.execute("SELECT device_id, name, area FROM device_meta")}
                      if "device_meta" in tables else {})
        if not self._broken:
            self._write_areas()

    def _take(self, doc: dict) -> bool:
        """Use what the file says; True when that differs from what we had."""
        areas = [str(a) for a in doc.get("areas") or []]
        meta = {str(k): {"name": (v or {}).get("name"), "area": (v or {}).get("area")}
                for k, v in (doc.get("devices") or {}).items() if isinstance(v, dict) or v is None}
        with self._lock:
            changed = (areas, meta) != (self._areas, self._meta)
            self._areas, self._meta = areas, meta
            self._broken = False
        return changed

    def _write_areas(self) -> None:
        if self._broken:
            log.warning("not saving rooms: %s has to be fixed first", self._areas_file.path.name)
            return
        self._areas_file.write({"areas": list(self._areas), "devices": {k: dict(v) for k, v in self._meta.items()}},
                               replace=True)
        self._dirty = False

    def flush(self) -> None:
        """Write changes that were held back (see set_device_meta)."""
        with self._lock:
            if self._dirty:
                self._write_areas()

    def reload_areas(self) -> bool:
        """Pick up a hand edit of areas.yaml. True when rooms or device names changed."""
        if not self._areas_file.changed():
            return False
        try:
            return self._take(self._areas_file.read())
        except ValueError as err:
            log.warning("%s (keeping the previous rooms)", err)
            self._broken = True
            return False

    def areas(self) -> list[str]:
        return list(self._areas)

    def add_area(self, name: str) -> None:
        with self._lock:
            if name not in self._areas:
                self._areas.append(name)
                self._write_areas()

    def remove_area(self, name: str) -> None:
        with self._lock:
            if name in self._areas:
                self._areas.remove(name)
            for meta in self._meta.values():
                if meta.get("area") == name:
                    meta["area"] = None
            self._write_areas()

    def device_meta(self, device_id: str) -> dict | None:
        meta = self._meta.get(device_id)
        return dict(meta) if meta is not None else None

    def set_device_meta(self, device_id: str, name: str | None, area: str | None, defer: bool = False) -> None:
        """defer=True: write the file a moment later (many devices appear at once when the hub starts)."""
        with self._lock:
            self._meta[device_id] = {"name": name, "area": area}
            self._dirty = True
            if not defer:
                self._write_areas()

    # entity state-since
    def since(self, device_id: str, key: str) -> tuple[str, float] | None:
        row = self.db.execute("SELECT state, since FROM entity_since WHERE device_id = ? AND key = ?",
                              (device_id, key)).fetchone()
        return (row["state"], row["since"]) if row else None

    def set_since(self, device_id: str, key: str, state: str, since: float) -> None:
        self.db.execute("INSERT OR REPLACE INTO entity_since (device_id, key, state, since) VALUES (?, ?, ?, ?)",
                        (device_id, key, state, since))
        self.db.commit()

    def presence_minutes(self, device_id: str) -> float | None:
        row = self.db.execute("SELECT minutes FROM presence_minutes WHERE device_id = ?", (device_id,)).fetchone()
        return row["minutes"] if row else None

    def set_presence_minutes(self, device_id: str, minutes: float) -> None:
        self.db.execute("INSERT OR REPLACE INTO presence_minutes (device_id, minutes) VALUES (?, ?)", (device_id, minutes))
        self.db.commit()

    # flow variables (washer status, post waiting, ...)
    def variables(self) -> dict[str, dict]:
        return {r["name"]: {"value": r["value"], "updated": r["updated"]}
                for r in self.db.execute("SELECT * FROM variables ORDER BY name")}

    def get_var(self, name: str) -> str | None:
        row = self.db.execute("SELECT value FROM variables WHERE name = ?", (name,)).fetchone()
        return row["value"] if row else None

    def set_var(self, name: str, value: str) -> None:
        import time
        self.db.execute("INSERT OR REPLACE INTO variables (name, value, updated) VALUES (?, ?, ?)",
                        (name, value, time.time()))
        self.db.commit()

    # history: history_days is 0 = keep forever (default), -1 = off, otherwise days to keep
    def history_days(self) -> int:
        return int(self.get("history_days") or 0)

    def set_history_days(self, days: int) -> None:
        self.set("history_days", str(days))
        self._prune_history()

    def add_history(self, device_id: str, key: str, value) -> float | None:
        """Record a change; returns when, or None if history is off."""
        days = self.history_days()
        if days < 0:
            return None
        now = time.time()
        self.db.execute("INSERT INTO history (ts, device_id, key, value) VALUES (?, ?, ?, ?)",
                        (now, device_id, key, json.dumps(value, default=str)))
        self.db.commit()
        if days > 0 and now - self._pruned > 3600:
            self._prune_history()
        return now

    def _prune_history(self) -> None:
        self._pruned = time.time()
        days = self.history_days()
        if days > 0:
            self.db.execute("DELETE FROM history WHERE ts < ?", (self._pruned - days * 86400,))
            self.db.commit()

    def history(self, device_id: str, limit: int = 200, since: float = 0) -> list[dict]:
        rows = self.db.execute("SELECT ts, key, value FROM history WHERE device_id = ? AND ts >= ? ORDER BY ts DESC, id DESC LIMIT ?",
                               (device_id, since, limit)).fetchall()
        return [{"ts": r["ts"], "key": r["key"], "value": json.loads(r["value"])} for r in rows]

    def last_history(self, device_id: str, key: str) -> tuple[float, object] | None:
        """When an entity last changed and to what, from its newest history row."""
        row = self.db.execute("SELECT ts, value FROM history WHERE device_id = ? AND key = ? ORDER BY ts DESC, id DESC LIMIT 1",
                              (device_id, key)).fetchone()
        return (row["ts"], json.loads(row["value"])) if row else None

    def hook_token(self) -> str:
        """Secret part of webhook URLs (used by ntfy notification buttons)."""
        token = self.get("hook_token")
        if not token:
            token = secrets.token_urlsafe(24)
            self.set("hook_token", token)
        return token
