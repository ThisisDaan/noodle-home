"""UniFi presence: which of your devices are on the Wi-Fi, read from your own UniFi controller. No cloud.

You list the devices to follow as "MAC=Name" pairs. Each becomes a device with a "Home" presence sensor that is
on while the controller sees it connected. Phones drop off Wi-Fi to save battery, so a device only counts as away
after it has been gone for AWAY_AFTER seconds.

Both kinds of controller work: the classic one (the Docker image, port 8443) and UniFi OS (a Dream Machine or
Cloud Key, port 443).
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from ... import config
from ...hub import Device, Entity, Hub

log = logging.getLogger(__name__)

POLL_EVERY = 20.0
AWAY_AFTER = 180.0  # seconds a device may be missing before it counts as away


def normalise(mac: str) -> str:
    return mac.strip().lower().replace("-", ":")


def present_macs(clients: list[dict]) -> set[str]:
    """The MAC addresses in the controller's list of connected clients."""
    return {normalise(c["mac"]) for c in clients if c.get("mac")}


def update_seen(seen: dict[str, float], present: set[str], tracked: set[str], now: float) -> dict[str, bool]:
    """Remember when each tracked device was last connected; say which are home (seen within AWAY_AFTER)."""
    for mac in present & tracked:
        seen[mac] = now
    return {mac: (now - seen.get(mac, -AWAY_AFTER * 2)) <= AWAY_AFTER for mac in tracked}


class UnifiAdapter:
    source = "unifi"
    extra_commands: frozenset[str] = frozenset()

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.http: httpx.AsyncClient | None = None
        self.connected = False
        self.error: str | None = None
        self.os_style = False  # UniFi OS (Dream Machine, Cloud Key) rather than the classic controller
        self._logged_in = False
        self._seen: dict[str, float] = {}

    def _base(self) -> str:
        url = config.UNIFI_URL.strip().rstrip("/")
        return url if url.startswith(("http://", "https://")) else f"https://{url}"

    async def _login(self) -> None:
        body = {"username": config.UNIFI_USERNAME, "password": config.UNIFI_PASSWORD}
        res = await self.http.post(f"{self._base()}/api/auth/login", json=body)  # UniFi OS
        if res.status_code == 404:
            res = await self.http.post(f"{self._base()}/api/login", json=body)  # the classic controller
            self.os_style = False
        else:
            self.os_style = True
        if res.status_code in (400, 401, 403):
            raise RuntimeError("Wrong username or password (use a local account of the controller)")
        res.raise_for_status()
        self._logged_in = True

    async def _clients(self) -> list[dict]:
        site = config.UNIFI_SITE or "default"
        for attempt in (1, 2):
            if not self._logged_in:
                await self._login()
            path = f"/proxy/network/api/s/{site}/stat/sta" if self.os_style else f"/api/s/{site}/stat/sta"
            res = await self.http.get(f"{self._base()}{path}")
            if res.status_code == 401 and attempt == 1:
                self._logged_in = False  # the session ran out: log in again
                continue
            res.raise_for_status()
            return res.json().get("data") or []
        raise RuntimeError("The controller refused the login")

    async def run(self) -> None:
        self.http = httpx.AsyncClient(timeout=10, verify=False)
        try:
            while True:
                if config.UNIFI_URL and config.UNIFI_USERNAME:
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
        self.tracked_changed()
        tracked = {normalise(mac): name for mac, name in config.UNIFI_DEVICES.items()}
        home = update_seen(self._seen, present_macs(await self._clients()), set(tracked), time.time())
        now = time.time()
        for mac, name in tracked.items():
            entity = Entity("home", "binary_sensor", "Home", state=home[mac], device_class="presence")
            device = self.hub.devices.get(f"unifi:{mac}")
            if device is None:
                device = Device(id=f"unifi:{mac}", source=self.source, name=name, manufacturer="UniFi", entities={"home": entity})
                device.available, device.last_seen = True, now
                self.hub.upsert(device)
                continue
            device.entities["home"].state = home[mac]
            device.name, device.available, device.last_seen = name, True, now
            self.hub.changed(device)

    def tracked_changed(self) -> None:
        """The list of devices was edited: forget the ones that were removed."""
        keep = {f"unifi:{normalise(mac)}" for mac in config.UNIFI_DEVICES}
        for device_id in [d.id for d in self.hub.devices.values() if d.source == self.source and d.id not in keep]:
            self.hub.remove(device_id)

    async def command(self, device: Device, entity: Entity, on, brightness, toggle, **extra) -> None:
        raise ValueError("A presence sensor cannot be controlled")
