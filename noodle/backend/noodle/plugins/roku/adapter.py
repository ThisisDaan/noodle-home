"""Roku players and TVs over their local External Control Protocol (HTTP, port 8060). No cloud, no account.

Each device gets a power switch, a play/pause switch and the app that is open. "Control by mobile apps" must be
on (Settings, System, Advanced system settings) for commands to be accepted. Search uses the devices' SSDP
announcement (multicast 239.255.255.250:1900), only while the user has pressed Search.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import unescape

from ...hub import Device, Entity
from ...udp import udp_probe
from ..lan.adapter import LanAdapter

PORT = 8060
SSDP = ("239.255.255.250", 1900)
SEARCH = b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: roku:ecp\r\n\r\n'


def tag(xml: str, name: str) -> str | None:
    m = re.search(rf"<{name}(?:\s[^>]*)?>(.*?)</{name}>", xml, re.S)
    return unescape(m.group(1).strip()) if m else None


def location_host(text: str) -> str | None:
    """The address in the LOCATION header of an SSDP answer (http://192.168.1.40:8060/)."""
    m = re.search(r"^location:\s*http://([^:/\s]+)", text, re.I | re.M)
    return m.group(1) if m else None


def entities_from(info: str, app: str | None, player: str | None) -> dict[str, Entity]:
    power = (tag(info, "power-mode") or "").lower()
    on = power in ("", "poweron", "on")  # standby shows as "ready", a TV with the screen off as "displayoff"
    entities = {
        "power": Entity("power", "switch", "Power", state=on),
        "playing": Entity("playing", "switch", "Playing", state=(player or "").lower() == "play"),
    }
    if app:
        entities["app"] = Entity("app", "sensor", "App", state=app)
    return entities


def keys_for(is_tv: bool, is_on: bool, want: bool) -> list[str]:
    """The key presses that put the power in the wanted state (none when it already is)."""
    if want == is_on:
        return []
    if is_tv:
        return ["PowerOn" if want else "PowerOff"]
    return ["Power"]  # players have one key that toggles between on and standby


def _host_reply(data: bytes, addr: tuple) -> str:
    return location_host(data.decode(errors="ignore")) or addr[0]


class RokuAdapter(LanAdapter):
    source = "roku"
    manufacturer = "Roku"
    setting, attr = "roku_devices", "ROKU_DEVICES"
    poll_every = 6.0

    async def _info(self, host: str) -> str:
        res = await self.http.get(f"http://{host}:{PORT}/query/device-info")
        res.raise_for_status()
        if "<device-info>" not in res.text:
            raise ValueError("not a Roku")
        return res.text

    async def identify(self, host):
        info = await self._info(host)
        key = (tag(info, "serial-number") or tag(info, "device-id") or host).lower()
        return key, tag(info, "user-device-name") or tag(info, "friendly-device-name") or "Roku"

    async def read(self, key, host):
        info = await self._info(host)
        app = player = None
        try:
            active = (await self.http.get(f"http://{host}:{PORT}/query/active-app")).text
            app = tag(active, "app")
            player = re.search(r'<player[^>]*state="(\w+)"', (await self.http.get(f"http://{host}:{PORT}/query/media-player")).text)
            player = player.group(1) if player else None
        except Exception:
            pass
        return Device(id=f"roku:{key}", source=self.source,
                      name=tag(info, "user-device-name") or tag(info, "friendly-device-name") or "Roku",
                      model=tag(info, "model-name"), manufacturer=self.manufacturer, entities=entities_from(info, app, player))

    async def _key(self, host: str, name: str) -> None:
        res = await self.http.post(f"http://{host}:{PORT}/keypress/{name}")
        res.raise_for_status()

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        want = (not entity.state) if toggle else on
        if want is None:
            return
        if entity.key == "power":
            is_tv = (tag(await self._info(host), "is-tv") or "").lower() == "true"
            for key in keys_for(is_tv, bool(entity.state), want):
                await self._key(host, key)
        elif entity.key == "playing" and want != bool(entity.state):
            await self._key(host, "Play")  # the same key plays and pauses

    # --- searching: one SSDP multicast, only while the user has pressed Search

    async def search(self, seconds, found):
        self.nearby.clear()
        seen: set[str] = set()
        async for host in udp_probe(SEARCH, SSDP[1], seconds, _host_reply, host=SSDP[0], multicast=True):
            if host in seen:
                continue
            seen.add(host)
            try:
                key, name = await self.identify(host)
            except Exception:
                continue
            if key not in self.known:
                self.nearby[key] = (host, name)
                found(key, name=name, detail=host)
