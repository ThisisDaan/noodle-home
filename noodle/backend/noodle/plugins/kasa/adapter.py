"""TP-Link Kasa plugs and bulbs over their local protocol (TCP port 9999). No cloud, no account.

The protocol is a JSON message scrambled with a simple XOR; plugs (HS/KP) and bulbs (KL/LB) are supported. Tapo
devices use a different, account-based protocol and are not supported.
"""

from __future__ import annotations

import asyncio
import json
import struct

from ...hub import Device, Entity
from ...udp import udp_probe
from ..lan.adapter import LanAdapter

PORT = 9999
SYSINFO = {"system": {"get_sysinfo": {}}}
BULB_SERVICE = "smartlife.iot.smartbulb.lightingservice"


def encrypt(data: dict, prefix: bool = True) -> bytes:
    """TCP messages start with the length (4 bytes); UDP messages do not."""
    plain = json.dumps(data).encode()
    key, out = 171, bytearray()
    for byte in plain:
        key ^= byte
        out.append(key)
    return (struct.pack(">I", len(out)) if prefix else b"") + bytes(out)


def decrypt(data: bytes) -> dict:
    key, out = 171, bytearray()
    for byte in data:
        out.append(key ^ byte)
        key = byte
    return json.loads(out.decode())


async def request(host: str, message: dict, timeout: float = 5.0) -> dict:
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, PORT), timeout)
    try:
        writer.write(encrypt(message))
        await writer.drain()
        size = struct.unpack(">I", await asyncio.wait_for(reader.readexactly(4), timeout))[0]
        if size > 65536:
            raise ValueError("answer too large")
        return decrypt(await asyncio.wait_for(reader.readexactly(size), timeout))
    finally:
        writer.close()


def entities_from(info: dict) -> dict[str, Entity]:
    if "light_state" in info:  # a bulb
        ls = info["light_state"]
        if "dft_on_state" in ls and not ls.get("on_off"):  # off: the last settings are kept in dft_on_state
            ls = {**ls["dft_on_state"], "on_off": 0}
        attrs = {"can": ["color_temp"], "color_temp": ls.get("color_temp") or 2700, "color_temp_range": [2500, 6500]}
        if info.get("is_color"):
            attrs["can"].append("color")
            attrs["color"] = {"h": ls.get("hue", 0), "s": ls.get("saturation", 0)}
        return {"light": Entity("light", "light", "Light", state=bool(ls.get("on_off")), brightness=ls.get("brightness"), attrs=attrs)}
    return {"switch": Entity("switch", "switch", "Switch", state=bool(info.get("relay_state")))}


def _sysinfo_reply(data: bytes, addr: tuple) -> tuple[str, str, str]:
    info = decrypt(data)["system"]["get_sysinfo"]
    key = str(info.get("deviceId") or addr[0]).lower()
    return key, str(info.get("alias") or info.get("model") or "Kasa"), addr[0]


class KasaAdapter(LanAdapter):
    source = "kasa"
    manufacturer = "TP-Link Kasa"
    setting, attr = "kasa_devices", "KASA_DEVICES"
    extra_commands = frozenset({"color_temp", "color"})

    async def _info(self, host: str) -> dict:
        reply = await request(host, SYSINFO)
        return reply["system"]["get_sysinfo"]

    async def identify(self, host):
        info = await self._info(host)
        return str(info.get("deviceId") or info.get("mic_mac") or host).lower(), str(info.get("alias") or info.get("model") or "Kasa")

    async def read(self, key, host):
        info = await self._info(host)
        entities = entities_from(info)
        try:  # a plug that measures energy
            emeter = (await request(host, {"emeter": {"get_realtime": {}}}))["emeter"]["get_realtime"]
            watts = emeter.get("power") if "power" in emeter else (emeter.get("power_mw", 0) / 1000)
            entities["power"] = Entity("power", "sensor", "Power", state=round(float(watts), 1), unit="W", device_class="power")
        except Exception:
            pass
        return Device(id=f"kasa:{key}", source=self.source, name=str(info.get("alias") or "Kasa"),
                      model=info.get("model"), manufacturer=self.manufacturer, entities=entities)

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        if entity.kind == "switch":
            want = (not entity.state) if toggle else on
            if want is not None:
                await request(host, {"system": {"set_relay_state": {"state": 1 if want else 0}}})
            return
        state: dict = {"ignore_default": 1, "transition_period": 300}
        want = (not entity.state) if toggle else on
        if brightness is not None:
            want = True
            state["brightness"] = brightness
        if "color_temp" in extra:
            want = True
            state.update(color_temp=extra["color_temp"], hue=0, saturation=0)
        if "color" in extra:
            want = True
            state.update(hue=round(extra["color"]["h"]) % 360, saturation=round(extra["color"]["s"]), color_temp=0)
        if want is not None:
            state["on_off"] = 1 if want else 0
        await request(host, {BULB_SERVICE: {"transition_light_state": state}})

    # --- searching: one UDP broadcast, only while the user has pressed Search

    async def search(self, seconds, found):
        self.nearby.clear()
        async for key, name, host in udp_probe(encrypt(SYSINFO, prefix=False), PORT, seconds, _sysinfo_reply):
            if key not in self.known:
                self.nearby[key] = (host, name)
                found(key, name=name, detail=host)
