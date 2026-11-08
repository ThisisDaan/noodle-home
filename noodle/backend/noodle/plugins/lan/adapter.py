"""The shared part of integrations for devices that sit on the local network and are reached by address
(Shelly, WLED, Kasa, Nanoleaf, Sonos). A subclass says how to recognise a device (`identify`), how to read it
(`read`) and how to command it (`send`); this class does the rest: it keeps the addresses the user added,
asks every device for its state every few seconds, marks silent ones offline and finds new ones.

Nothing searches in the background. `search` runs only while the user has pressed Search (it listens for the
devices' mDNS announcements for a short time); the devices the user adds are saved with their address and
polled by address from then on.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from ... import config
from ...hub import Device, Entity, Hub

log = logging.getLogger(__name__)

POLL_TIMEOUT = 5.0


class LanAdapter:
    source = ""
    manufacturer = ""
    setting = ""  # config setting that holds {key: address} of the devices the user added
    attr = ""  # the config attribute of the same setting
    mdns: tuple[str, ...] = ()  # service types announced by the devices, e.g. "_wled._tcp.local."
    poll_every = 8.0
    gone_after = 30.0
    extra_commands: frozenset[str] = frozenset()

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.known: dict[str, str] = {}  # the devices the user added: key -> address
        self.nearby: dict[str, tuple[str, str]] = {}  # found by a search, not added: key -> (address, name)
        self.names: dict[str, str] = {}
        self.heard: dict[str, float] = {}
        self.http: httpx.AsyncClient | None = None
        self.running = False

    # --- what a subclass provides

    async def identify(self, host: str) -> tuple[str, str]:
        """(a key that stays the same for this device, its name). Raise if nothing of this kind answers."""
        raise NotImplementedError

    async def read(self, key: str, host: str) -> Device:
        """The device as it is right now."""
        raise NotImplementedError

    async def send(self, device: Device, entity: Entity, host: str, on: bool | None, brightness: int | None,
                   toggle: bool, **extra) -> None:
        raise NotImplementedError

    # --- connection

    async def run(self) -> None:
        self.http = httpx.AsyncClient(timeout=POLL_TIMEOUT, verify=False)
        self.known = dict(getattr(config, self.attr))
        self.running = True
        log.info("%s: %d saved device(s)", self.source, len(self.known))
        try:
            while True:
                await asyncio.gather(*(self.refresh(key) for key in list(self.known)))
                self._check_gone(time.time())
                await asyncio.sleep(self.poll_every)
        finally:
            self.running = False
            await self.http.aclose()
            self.http = None

    async def refresh(self, key: str) -> None:
        host = self.known.get(key)
        if host is None:
            return
        try:
            device = await self.read(key, host)
        except Exception as err:
            log.debug("%s %s (%s): %s", self.source, key, host, err)
            return
        self.heard[key] = time.time()
        device.available = True
        device.last_seen = self.heard[key]
        self.names[key] = device.name
        old = self.hub.devices.get(device.id)
        if old is None:
            self.hub.upsert(device)
            return
        for k, e in device.entities.items():  # keep what the hub already tracks, update the readings
            if k in old.entities:
                old.entities[k].state, old.entities[k].brightness = e.state, e.brightness
                old.entities[k].attrs, old.entities[k].unit = e.attrs, e.unit
            else:
                old.entities[k] = e
        old.available, old.last_seen = True, device.last_seen
        self.hub.changed(old)

    def _check_gone(self, now: float) -> None:
        for key in self.known:
            device = self.hub.devices.get(f"{self.source}:{key}")
            if device and device.available and now - self.heard.get(key, 0) > self.gone_after:
                device.available = False
                self.hub.changed(device)

    # --- adding and removing, only when the user asks

    def _save(self) -> None:
        config.save({self.setting: dict(self.known)})

    async def add_host(self, host: str) -> str:
        """Add a device by its address. Returns its key."""
        host = host.strip().removeprefix("http://").removeprefix("https://").rstrip("/")
        if not host or "=" in host or "," in host:
            raise ValueError("Enter the IP address of the device, like 192.168.1.40")
        if self.http is None:
            raise RuntimeError(f"{self.source} is not running")
        try:
            key, name = await self.identify(host)
        except (httpx.HTTPError, OSError, asyncio.TimeoutError) as err:
            raise ValueError(f"Nothing answered at {host} ({err.__class__.__name__})") from err
        self.known[key] = host
        self.names[key] = name
        self._save()
        await self.refresh(key)
        return key

    async def add_found(self, key: str) -> None:
        found = self.nearby.get(key)
        if found is None:
            raise KeyError("That device is no longer in the list; search again")
        await self.add_host(found[0])
        self.nearby.pop(key, None)  # only once it was added: a button press may still be needed, and then it is asked again

    def forget(self, key: str) -> None:
        self.known.pop(key, None)
        self.heard.pop(key, None)
        self.hub.remove(f"{self.source}:{key}")
        self._save()

    def device_list(self) -> list[dict]:
        out = []
        for key, host in self.known.items():
            device = self.hub.devices.get(f"{self.source}:{key}")
            out.append({"key": key, "name": self.names.get(key) or (device.name if device else key),
                        "address": host, "available": bool(device and device.available)})
        return out

    # --- searching: only while the user has pressed Search

    async def search(self, seconds: float, found) -> None:
        if not self.mdns:
            raise RuntimeError("Add this device by its address")
        if self.http is None:
            raise RuntimeError(f"{self.source} is not running")
        from ... import mdns

        self.nearby.clear()

        async def on_service(service_type, name, info) -> None:
            for host in mdns.ipv4(info):
                try:
                    key, label = await self.identify(host)
                except Exception:
                    continue
                if key not in self.known and host not in self.known.values():  # (a key can differ before pairing)
                    self.nearby[key] = (host, label)
                    found(key, name=label, detail=host)
                return

        await mdns.browse(list(self.mdns), seconds, on_service)

    # --- control

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool,
                      **extra) -> None:
        key = device.id.split(":", 1)[1]
        host = self.known.get(key)
        if host is None or not self.running:
            raise RuntimeError(f"{device.name} is not reachable")
        await self.send(device, entity, host, on, brightness, toggle, **extra)
        await self.refresh(key)
