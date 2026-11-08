"""Philips WiZ bulbs and plugs over their local UDP protocol (port 38899). No cloud, no account.

Each request is one JSON datagram and each answer is one JSON datagram. Bulbs with "RGB" in their module name
(ESP01_SHRGB...) do colour, "SOCKET" modules are plugs, anything else is a white or tunable-white bulb.
"""

from __future__ import annotations

import asyncio
import colorsys
import json

from ...hub import Device, Entity
from ...udp import udp_probe
from ..lan.adapter import LanAdapter

PORT = 38899
TEMP_RANGE = [2200, 6500]
REGISTER = {"method": "registration", "params": {"phoneMac": "AAAAAAAAAAAA", "register": False, "phoneIp": "1.2.3.4", "id": "1"}}


class _Once(asyncio.DatagramProtocol):
    def __init__(self, future: asyncio.Future) -> None:
        self.future = future

    def datagram_received(self, data, addr) -> None:
        if not self.future.done():
            self.future.set_result(data)

    def error_received(self, exc) -> None:
        if not self.future.done():
            self.future.set_exception(exc)


async def request(host: str, message: dict, timeout: float = 3.0) -> dict:
    """Send one message and wait for the answer. Raises OSError / TimeoutError when nothing answers."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    transport, _ = await loop.create_datagram_endpoint(lambda: _Once(future), remote_addr=(host, PORT))
    try:
        transport.sendto(json.dumps(message).encode())
        reply = json.loads(await asyncio.wait_for(future, timeout))
    finally:
        transport.close()
    if "error" in reply:
        raise ValueError(str(reply["error"]))
    return reply


def kind_of(module: str) -> str:
    """"color", "white" or "plug", from the module name such as ESP01_SHRGB_03 or ESP10_SOCKET_06."""
    module = (module or "").upper()
    return "plug" if "SOCKET" in module else "color" if "RGB" in module else "white"


def entities_from(pilot: dict, module: str = "") -> dict[str, Entity]:
    kind = kind_of(module)
    if kind == "plug":
        return {"switch": Entity("switch", "switch", "Switch", state=bool(pilot.get("state")))}
    attrs: dict = {"can": ["color_temp"], "color_temp": pilot.get("temp") or 2700, "color_temp_range": TEMP_RANGE}
    if kind == "color" or "r" in pilot:
        attrs["can"].append("color")
        h, s, _ = colorsys.rgb_to_hsv(pilot.get("r", 255) / 255, pilot.get("g", 255) / 255, pilot.get("b", 255) / 255)
        attrs["color"] = {"h": round(h * 360, 1), "s": round(s * 100, 1)}
    return {"light": Entity("light", "light", "Light", state=bool(pilot.get("state")), brightness=pilot.get("dimming", 100), attrs=attrs)}


def pilot_for(on: bool | None, brightness: int | None, color_temp: int | None, color: dict | None) -> dict:
    """The setPilot parameters for a command. A colour or temperature or brightness also turns the light on."""
    params: dict = {}
    if brightness is not None:
        on = True
        params["dimming"] = max(10, min(100, brightness))  # WiZ does not go below 10 %
    if color_temp is not None:
        on = True
        params["temp"] = max(TEMP_RANGE[0], min(TEMP_RANGE[1], color_temp))
    if color is not None:
        on = True
        r, g, b = colorsys.hsv_to_rgb(color["h"] / 360, color["s"] / 100, 1.0)
        params.update(r=round(r * 255), g=round(g * 255), b=round(b * 255))
    if on is not None:
        params["state"] = on
    return params


def _mac_reply(data: bytes, addr: tuple) -> tuple[str, str]:
    return str(json.loads(data)["result"]["mac"]).lower().replace(":", ""), addr[0]


class WizAdapter(LanAdapter):
    source = "wiz"
    manufacturer = "WiZ"
    setting, attr = "wiz_devices", "WIZ_DEVICES"
    extra_commands = frozenset({"color_temp", "color"})

    async def _module(self, host: str) -> str:
        try:
            return str((await request(host, {"method": "getSystemConfig", "params": {}}))["result"].get("moduleName") or "")
        except Exception:
            return ""

    async def identify(self, host):
        result = (await request(host, {"method": "getPilot", "params": {}}))["result"]
        mac = str(result.get("mac") or host).lower().replace(":", "")
        return mac, f"WiZ {mac[-4:]}"

    async def read(self, key, host):
        pilot = (await request(host, {"method": "getPilot", "params": {}}))["result"]
        module = await self._module(host)
        return Device(id=f"wiz:{key}", source=self.source, name=self.names.get(key) or f"WiZ {key[-4:]}",
                      model=module or None, manufacturer=self.manufacturer, entities=entities_from(pilot, module))

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        want = (not entity.state) if toggle else on
        params = pilot_for(want, brightness, extra.get("color_temp"), extra.get("color"))
        if params:
            await request(host, {"method": "setPilot", "params": params})

    # --- searching: one UDP broadcast, only while the user has pressed Search

    async def search(self, seconds, found):
        self.nearby.clear()
        async for mac, host in udp_probe(json.dumps(REGISTER).encode(), PORT, seconds, _mac_reply):
            if mac not in self.known:
                name = f"WiZ {mac[-4:]}"
                self.nearby[mac] = (host, name)
                found(mac, name=name, detail=host)
