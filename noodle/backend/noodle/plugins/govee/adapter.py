"""Govee lights over Govee's LAN API (UDP). No cloud, no account.

"LAN Control" has to be switched on for each light in the Govee Home app (Device settings), and only some models
have it. Devices listen on port 4003 (and 4001 for the scan); they answer to port 4002 on this machine, so one
exchange at a time uses that port. Search sends the scan to the multicast group 239.255.255.250.
"""

from __future__ import annotations

import asyncio
import json
import socket
import time

from ...hub import Device, Entity
from ...udp import udp_probe
from ..lan.adapter import LanAdapter

GROUP = ("239.255.255.250", 4001)
CONTROL_PORT = 4003
REPLY_PORT = 4002
SCAN = {"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}
STATUS = {"msg": {"cmd": "devStatus", "data": {}}}
TEMP_RANGE = [2000, 9000]
_port = asyncio.Lock()  # only one exchange can listen on the reply port at a time


def message(cmd: str, **data) -> dict:
    return {"msg": {"cmd": cmd, "data": data}}


def parse(raw: bytes) -> tuple[str, dict]:
    """(command, data) of a reply. Raises ValueError when it is not a Govee message."""
    try:
        msg = json.loads(raw)["msg"]
        return str(msg["cmd"]), dict(msg.get("data") or {})
    except (KeyError, TypeError, ValueError) as err:
        raise ValueError("not a Govee message") from err


def device_key(device_id: str) -> str:
    return device_id.lower().replace(":", "")


def entities_from(status: dict) -> dict[str, Entity]:
    color = status.get("color") or {}
    attrs: dict = {"can": ["color_temp", "color"], "color_temp": status.get("colorTemInKelvin") or 2700,
                   "color_temp_range": TEMP_RANGE}
    if color:
        import colorsys
        h, s, _ = colorsys.rgb_to_hsv(color.get("r", 255) / 255, color.get("g", 255) / 255, color.get("b", 255) / 255)
        attrs["color"] = {"h": round(h * 360, 1), "s": round(s * 100, 1)}
    return {"light": Entity("light", "light", "Light", state=bool(status.get("onOff")),
                            brightness=status.get("brightness", 100), attrs=attrs)}


def commands_for(on: bool | None, brightness: int | None, color_temp: int | None, color: dict | None) -> list[dict]:
    """The messages for a command, in order. Anything but an off command turns the light on first."""
    if on is False:
        return [message("turn", value=0)]
    out: list[dict] = []
    if on or brightness is not None or color_temp is not None or color is not None:
        out.append(message("turn", value=1))
    if brightness is not None:
        out.append(message("brightness", value=max(1, min(100, brightness))))
    if color_temp is not None:
        out.append(message("colorwc", color={"r": 0, "g": 0, "b": 0},
                           colorTemInKelvin=max(TEMP_RANGE[0], min(TEMP_RANGE[1], color_temp))))
    if color is not None:
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(color["h"] / 360, color["s"] / 100, 1.0)
        out.append(message("colorwc", color={"r": round(r * 255), "g": round(g * 255), "b": round(b * 255)}, colorTemInKelvin=0))
    return out


async def exchange(host: str, port: int, payload: dict, expect: str, timeout: float = 3.0) -> dict:
    """Send one message to a device and return the data of its answer. Raises when nothing answers."""
    async with _port:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        loop = asyncio.get_running_loop()
        try:
            sock.bind(("", REPLY_PORT))
            await loop.sock_sendto(sock, json.dumps(payload).encode(), (host, port))
            deadline = time.time() + timeout
            while True:
                left = deadline - time.time()
                if left <= 0:
                    raise asyncio.TimeoutError(f"{host} did not answer")
                raw, addr = await asyncio.wait_for(loop.sock_recvfrom(sock, 4096), left)
                if addr[0] != host:
                    continue
                cmd, data = parse(raw)
                if cmd == expect:
                    return data
        finally:
            sock.close()


async def send_only(host: str, payload: dict) -> None:
    """Commands get no answer."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
        await asyncio.get_running_loop().sock_sendto(sock, json.dumps(payload).encode(), (host, CONTROL_PORT))
    finally:
        sock.close()


def _scan_reply(raw: bytes, addr: tuple) -> tuple[str, str, str] | None:
    cmd, data = parse(raw)
    key = device_key(str(data.get("device") or ""))
    if cmd != "scan" or not key:
        return None
    return key, str(data.get("sku") or ""), str(data.get("ip") or addr[0])


class GoveeAdapter(LanAdapter):
    source = "govee"
    manufacturer = "Govee"
    setting, attr = "govee_devices", "GOVEE_DEVICES"
    extra_commands = frozenset({"color_temp", "color"})

    def __init__(self, hub) -> None:
        super().__init__(hub)
        self.models: dict[str, str] = {}  # key -> model (sku), learned when the device was identified

    async def identify(self, host):
        data = await exchange(host, GROUP[1], SCAN, "scan")
        key = device_key(str(data.get("device") or host))
        sku = str(data.get("sku") or "")
        self.models[key] = sku
        return key, f"Govee {sku}".strip() if sku else "Govee"

    async def read(self, key, host):
        status = await exchange(host, CONTROL_PORT, STATUS, "devStatus")
        if key not in self.models:  # after a restart: ask the light which model it is
            try:
                self.models[key] = str((await exchange(host, GROUP[1], SCAN, "scan")).get("sku") or "")
            except Exception:
                self.models[key] = ""
        sku = self.models.get(key, "")
        return Device(id=f"govee:{key}", source=self.source, name=self.names.get(key) or (f"Govee {sku}".strip() if sku else "Govee"),
                      model=sku or None, manufacturer=self.manufacturer, entities=entities_from(status))

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        want = (not entity.state) if toggle else on
        for payload in commands_for(want, brightness, extra.get("color_temp"), extra.get("color")):
            await send_only(host, payload)

    # --- searching: one multicast scan, only while the user has pressed Search

    async def search(self, seconds, found):
        self.nearby.clear()
        async with _port:  # the replies come to REPLY_PORT, which only one exchange can hold
            async for key, sku, host in udp_probe(json.dumps(SCAN).encode(), GROUP[1], seconds, _scan_reply,
                                                  host=GROUP[0], multicast=True, bind=REPLY_PORT):
                if key in self.known:
                    continue
                self.models[key] = sku
                name = f"Govee {sku}".strip() if sku else "Govee"
                self.nearby[key] = (host, name)
                found(key, name=name, detail=host)
