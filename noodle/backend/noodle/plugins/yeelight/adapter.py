"""Yeelight bulbs over their LAN control protocol (JSON lines on TCP port 55443). No cloud, no account.

"LAN Control" has to be switched on for each bulb in the Yeelight app (Device settings). Search uses the
bulbs' SSDP announcement (UDP multicast 239.255.255.250:1982), only while the user has pressed Search.
"""

from __future__ import annotations

import asyncio
import json
import socket

from ...hub import Device, Entity
from ...udp import udp_probe
from ..lan.adapter import LanAdapter

PORT = 55443
SSDP = ("239.255.255.250", 1982)
SEARCH = b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1982\r\nMAN: "ssdp:discover"\r\nST: wifi_bulb\r\n\r\n'
PROPS = ["power", "bright", "ct", "hue", "sat", "color_mode", "name"]
CT_RANGE = [1700, 6500]


def parse_ssdp(text: str) -> dict:
    """The headers of an SSDP answer, lower-cased: id, model, name, location (yeelight://host:port), ..."""
    headers = {}
    for line in text.splitlines()[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return headers


def host_of(headers: dict) -> str | None:
    location = headers.get("location", "")
    if not location.startswith("yeelight://"):
        return None
    return location.removeprefix("yeelight://").split(":")[0] or None


def entities_from(props: dict) -> dict[str, Entity]:
    attrs: dict = {"can": ["color_temp"], "color_temp": int(props.get("ct") or 2700), "color_temp_range": CT_RANGE}
    if props.get("hue") not in (None, ""):  # only colour models report a hue
        attrs["can"].append("color")
        attrs["color"] = {"h": float(props["hue"]), "s": float(props.get("sat") or 0)}
    return {"light": Entity("light", "light", "Light", state=props.get("power") == "on",
                            brightness=int(props.get("bright") or 0), attrs=attrs)}


def commands_for(on: bool | None, brightness: int | None, color_temp: int | None, color: dict | None) -> list[tuple[str, list]]:
    """The (method, params) calls for a command, in order. Anything but an off command turns the light on first."""
    smooth = ["smooth", 300]
    if on is False:
        return [("set_power", ["off", *smooth])]
    calls: list[tuple[str, list]] = []
    if on or brightness is not None or color_temp is not None or color is not None:
        calls.append(("set_power", ["on", *smooth]))
    if brightness is not None:
        calls.append(("set_bright", [max(1, min(100, brightness)), *smooth]))
    if color_temp is not None:
        calls.append(("set_ct_abx", [max(CT_RANGE[0], min(CT_RANGE[1], color_temp)), *smooth]))
    if color is not None:
        calls.append(("set_hsv", [round(color["h"]) % 360, round(color["s"]), *smooth]))
    return calls


async def call(host: str, method: str, params: list, timeout: float = 4.0):
    """One command. Returns the "result" list. Raises when the bulb refuses (LAN control off) or is silent."""
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, PORT), timeout)
    try:
        writer.write(json.dumps({"id": 1, "method": method, "params": params}).encode() + b"\r\n")
        await writer.drain()
        while True:  # the bulb may send notifications first; wait for our answer
            reply = json.loads(await asyncio.wait_for(reader.readline(), timeout))
            if reply.get("id") == 1:
                break
    finally:
        writer.close()
    if "error" in reply:
        raise ValueError(str(reply["error"].get("message") or reply["error"]))
    return reply["result"]


async def ssdp_id(host: str, timeout: float = 2.0) -> dict:
    """Ask one bulb to announce itself (unicast), for its id and name. {} when it does not answer."""
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
        sock.sendto(SEARCH, (host, SSDP[1]))
        data, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 4096), timeout)
        return parse_ssdp(data.decode(errors="ignore"))
    except (asyncio.TimeoutError, OSError):
        return {}
    finally:
        sock.close()


def _bulb_reply(data: bytes, addr: tuple) -> tuple[str, str, str] | None:
    headers = parse_ssdp(data.decode(errors="ignore"))
    key = str(headers.get("id") or "").lower()
    if not key:
        return None
    return key, headers.get("name") or f"Yeelight {key[-4:]}", host_of(headers) or addr[0]


class YeelightAdapter(LanAdapter):
    source = "yeelight"
    manufacturer = "Yeelight"
    setting, attr = "yeelight_devices", "YEELIGHT_DEVICES"
    extra_commands = frozenset({"color_temp", "color"})

    async def identify(self, host):
        values = await call(host, "get_prop", ["name"])  # raises when LAN control is off
        headers = await ssdp_id(host)
        key = str(headers.get("id") or host).lower()
        return key, str(values[0] or headers.get("name") or "Yeelight")

    async def read(self, key, host):
        values = await call(host, "get_prop", PROPS)
        props = dict(zip(PROPS, values))
        return Device(id=f"yeelight:{key}", source=self.source, name=str(props.get("name") or self.names.get(key) or "Yeelight"),
                      manufacturer=self.manufacturer, entities=entities_from(props))

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        want = (not entity.state) if toggle else on
        for method, params in commands_for(want, brightness, extra.get("color_temp"), extra.get("color")):
            await call(host, method, params)

    # --- searching: one SSDP multicast, only while the user has pressed Search

    async def search(self, seconds, found):
        self.nearby.clear()
        async for key, name, host in udp_probe(SEARCH, SSDP[1], seconds, _bulb_reply, host=SSDP[0], multicast=True):
            if key not in self.known:
                self.nearby[key] = (host, name)
                found(key, name=name, detail=host)
