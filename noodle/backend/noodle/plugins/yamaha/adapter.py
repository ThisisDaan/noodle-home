"""Yamaha MusicCast receivers, speakers and soundbars over their local HTTP API (Extended Control). No cloud.

Each device gets a power switch, a volume number and a mute switch for its main zone.
"""

from __future__ import annotations

from ...hub import Device, Entity
from ..lan.adapter import LanAdapter

BASE = "/YamahaExtendedControl/v1"


def entities_from(status: dict) -> dict[str, Entity]:
    top = max(1, int(status.get("max_volume") or 100))
    return {
        "power": Entity("power", "switch", "Power", state=status.get("power") == "on"),
        "volume": Entity("volume", "number", "Volume", state=int(status.get("volume") or 0),
                         attrs={"min": 0, "max": top, "step": 1}),
        "mute": Entity("mute", "switch", "Muted", state=bool(status.get("mute"))),
    }


def check(reply: dict) -> dict:
    """MusicCast answers {"response_code": 0, ...}; anything else is an error."""
    if reply.get("response_code", 0) != 0:
        raise ValueError(f"the device refused (code {reply.get('response_code')})")
    return reply


class YamahaAdapter(LanAdapter):
    source = "yamaha"
    manufacturer = "Yamaha"
    setting, attr = "yamaha_devices", "YAMAHA_DEVICES"
    mdns = ("_musiccast._tcp.local.",)
    poll_every = 6.0

    async def _get(self, host: str, path: str) -> dict:
        res = await self.http.get(f"http://{host}{BASE}{path}")
        res.raise_for_status()
        return check(res.json())

    async def _name(self, host: str) -> str:
        try:
            return str((await self._get(host, "/system/getNetworkStatus")).get("network_name") or "")
        except Exception:
            return ""

    async def identify(self, host):
        info = await self._get(host, "/system/getDeviceInfo")
        key = str(info.get("device_id") or host).lower()
        return key, await self._name(host) or str(info.get("model_name") or "Yamaha")

    async def read(self, key, host):
        status = await self._get(host, "/main/getStatus")
        name = await self._name(host)
        return Device(id=f"yamaha:{key}", source=self.source, name=name or self.names.get(key) or "Yamaha",
                      manufacturer=self.manufacturer, entities=entities_from(status))

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        if entity.key == "volume":
            value = extra.get("value")
            if value is not None:
                top = int(entity.attrs.get("max") or 100)
                await self._get(host, f"/main/setVolume?volume={max(0, min(top, round(value)))}")
            return
        want = (not entity.state) if toggle else on
        if want is None:
            return
        if entity.key == "power":
            await self._get(host, f"/main/setPower?power={'on' if want else 'standby'}")
        elif entity.key == "mute":
            await self._get(host, f"/main/setMute?enable={'true' if want else 'false'}")
