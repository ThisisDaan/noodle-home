"""WLED LED strips over their local JSON API (/json). No cloud."""

from __future__ import annotations

import colorsys

from ..hub import Device, Entity
from .lan import LanAdapter


def rgb_to_hs(r: int, g: int, b: int) -> dict:
    h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return {"h": round(h * 360, 1), "s": round(s * 100, 1)}


def hs_to_rgb(h: float, s: float) -> list[int]:
    r, g, b = colorsys.hsv_to_rgb(h / 360, s / 100, 1.0)
    return [round(r * 255), round(g * 255), round(b * 255)]


def light_entity(state: dict) -> Entity:
    seg = (state.get("seg") or [{}])[0]
    rgb = (seg.get("col") or [[255, 255, 255]])[0][:3]
    return Entity("light", "light", "Light", state=bool(state.get("on")), brightness=round((state.get("bri") or 0) / 255 * 100),
                  attrs={"can": ["color"], "color": rgb_to_hs(*rgb)})


class WledAdapter(LanAdapter):
    source = "wled"
    manufacturer = "WLED"
    setting, attr = "wled_devices", "WLED_DEVICES"
    mdns = ("_wled._tcp.local.",)
    extra_commands = frozenset({"color"})

    async def _json(self, host: str) -> dict:
        res = await self.http.get(f"http://{host}/json")
        res.raise_for_status()
        data = res.json()
        if "state" not in data or "info" not in data:
            raise ValueError("not WLED")
        return data

    async def identify(self, host):
        info = (await self._json(host))["info"]
        key = str(info.get("mac") or host).lower()
        return key, str(info.get("name") or "WLED")

    async def read(self, key, host):
        data = await self._json(host)
        info = data["info"]
        return Device(id=f"wled:{key}", source=self.source, name=str(info.get("name") or "WLED"),
                      model=f"WLED {info.get('ver', '')}".strip(), manufacturer=self.manufacturer,
                      entities={"light": light_entity(data["state"])})

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        body: dict = {}
        if toggle:
            body["on"] = "t"
        elif on is not None:
            body["on"] = on
        if brightness is not None:
            body["on"] = True
            body["bri"] = max(1, round(brightness / 100 * 255))
        if "color" in extra:
            body["on"] = True
            body["seg"] = [{"col": [hs_to_rgb(extra["color"]["h"], extra["color"]["s"])]}]
        res = await self.http.post(f"http://{host}/json/state", json=body)
        res.raise_for_status()
