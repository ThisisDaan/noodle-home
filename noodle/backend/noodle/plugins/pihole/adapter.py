"""Pi-hole (version 6 and later) over its local API. No cloud.

One device, "Pi-hole": a switch that turns ad blocking on or off, and readings of today's queries, how many were
blocked and how many domains are on the blocklists. The password is the one for the Pi-hole web interface (or an
app password); it is exchanged for a session that is renewed when it runs out.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from ... import config
from ...hub import Device, Entity, Hub

log = logging.getLogger(__name__)

POLL_EVERY = 15.0
DEVICE_ID = "pihole:main"


def entities_from(summary: dict, blocking: dict) -> dict[str, Entity]:
    queries, gravity = summary.get("queries") or {}, summary.get("gravity") or {}
    return {
        "blocking": Entity("blocking", "switch", "Blocking ads", state=blocking.get("blocking") == "enabled"),
        "queries": Entity("queries", "sensor", "Queries today", state=int(queries.get("total") or 0)),
        "blocked": Entity("blocked", "sensor", "Blocked today", state=int(queries.get("blocked") or 0)),
        "percent": Entity("percent", "sensor", "Blocked", state=round(float(queries.get("percent_blocked") or 0), 1), unit="%"),
        "domains": Entity("domains", "sensor", "Domains on blocklists", state=int(gravity.get("domains_being_blocked") or 0)),
    }


class PiholeAdapter:
    source = "pihole"
    extra_commands: frozenset[str] = frozenset()

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.http: httpx.AsyncClient | None = None
        self.connected = False
        self.error: str | None = None
        self._sid: str | None = None

    def _base(self) -> str:
        url = config.PIHOLE_URL.strip().rstrip("/")
        return url if url.startswith(("http://", "https://")) else f"http://{url}"

    async def _login(self) -> None:
        res = await self.http.post(f"{self._base()}/api/auth", json={"password": config.PIHOLE_PASSWORD})
        if res.status_code == 401:
            raise RuntimeError("Wrong password")
        res.raise_for_status()
        session = res.json().get("session") or {}
        if not session.get("valid"):
            raise RuntimeError("Pi-hole did not accept the password")
        self._sid = session.get("sid")

    async def _call(self, method: str, path: str, **kwargs) -> dict:
        for attempt in (1, 2):
            if self._sid is None and config.PIHOLE_PASSWORD:
                await self._login()
            headers = {"sid": self._sid} if self._sid else {}
            res = await self.http.request(method, f"{self._base()}/api{path}", headers=headers, **kwargs)
            if res.status_code == 401 and attempt == 1:
                self._sid = None  # the session ran out: log in again
                continue
            res.raise_for_status()
            return res.json() if res.content else {}
        raise RuntimeError("Pi-hole refused the login")

    async def run(self) -> None:
        self.http = httpx.AsyncClient(timeout=8, verify=False)
        try:
            while True:
                if config.PIHOLE_URL:
                    try:
                        await self.refresh()
                        self.connected, self.error = True, None
                    except Exception as err:
                        self.connected, self.error = False, str(err) or err.__class__.__name__
                await asyncio.sleep(POLL_EVERY)
        finally:
            await self.http.aclose()
            self.http = None

    async def refresh(self) -> None:
        summary = await self._call("GET", "/stats/summary")
        blocking = await self._call("GET", "/dns/blocking")
        entities = entities_from(summary, blocking)
        now = time.time()
        device = self.hub.devices.get(DEVICE_ID)
        if device is None:
            device = Device(id=DEVICE_ID, source=self.source, name="Pi-hole", manufacturer="Pi-hole", entities=entities)
            device.available, device.last_seen = True, now
            self.hub.upsert(device)
            return
        for key, e in entities.items():
            old = device.entities.get(key)
            if old is None:
                device.entities[key] = e
            else:
                old.state = e.state
        device.available, device.last_seen = True, now
        self.hub.changed(device)

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool,
                      **extra) -> None:
        if not self.connected or self.http is None:
            raise RuntimeError("Pi-hole is not reachable")
        if entity.key != "blocking":
            return
        want = (not entity.state) if toggle else on
        if want is None:
            return
        await self._call("POST", "/dns/blocking", json={"blocking": bool(want), "timer": None})
        await self.refresh()
