"""Nanoleaf light panels, Canvas and Shapes over their local API (port 16021). No cloud.

Pairing: hold the power button for 5-7 seconds until the lights flash, then add the device within 30 seconds.
The token the panels give is saved (in secrets.yaml) and used from then on.
"""

from __future__ import annotations

import httpx

from ... import config
from ...hub import Device, Entity
from ..base import PressButton
from ..lan.adapter import LanAdapter

PORT = 16021


def light_entity(state: dict) -> Entity:
    def val(name: str, default=0):
        item = state.get(name) or {}
        return item.get("value", default) if isinstance(item, dict) else default

    ct = state.get("ct") or {}
    attrs = {"can": ["color_temp", "color"], "color_temp": val("ct", 4000),
             "color_temp_range": [ct.get("min", 1200), ct.get("max", 6500)],
             "color": {"h": val("hue"), "s": val("sat")}}
    return Entity("light", "light", "Light", state=bool(val("on", False)), brightness=val("brightness"), attrs=attrs)


class NanoleafAdapter(LanAdapter):
    source = "nanoleaf"
    manufacturer = "Nanoleaf"
    setting, attr = "nanoleaf_devices", "NANOLEAF_DEVICES"
    mdns = ("_nanoleafapi._tcp.local.",)
    extra_commands = frozenset({"color_temp", "color"})

    def _url(self, key: str, path: str = "") -> str:
        return f"http://{self.known[key]}:{PORT}/api/v1/{config.NANOLEAF_TOKENS[key]}{path}"

    async def identify(self, host):
        """A Nanoleaf answers 401 without a token. Its key is unknown until it is paired, so the search uses the address."""
        res = await self.http.get(f"http://{host}:{PORT}/api/v1/")
        if res.status_code not in (401, 403):
            raise ValueError("not a Nanoleaf")
        return f"nanoleaf-{host}", "Nanoleaf"

    async def add_host(self, host):
        host = host.strip().removeprefix("http://").rstrip("/").split(":")[0]
        if not host:
            raise ValueError("Enter the IP address of the Nanoleaf, like 192.168.1.40")
        if self.http is None:
            raise RuntimeError("Nanoleaf is not running")
        try:
            res = await self.http.post(f"http://{host}:{PORT}/api/v1/new")
        except (httpx.HTTPError, OSError) as err:
            raise ValueError(f"Nothing answered at {host} ({err.__class__.__name__})") from err
        if res.status_code == 403:
            raise PressButton("Hold the power button of the Nanoleaf for 5-7 seconds until the lights flash.")
        res.raise_for_status()
        token = res.json()["auth_token"]
        info = (await self.http.get(f"http://{host}:{PORT}/api/v1/{token}/")).json()
        key = str(info.get("serialNo") or host).lower().replace(",", "").replace("=", "")
        self.known[key] = host
        self.names[key] = info.get("name") or "Nanoleaf"
        config.save({"nanoleaf_tokens": {**config.NANOLEAF_TOKENS, key: token}})
        self._save()
        await self.refresh(key)
        return key

    def forget(self, key):
        super().forget(key)
        config.save({"nanoleaf_tokens": {k: v for k, v in config.NANOLEAF_TOKENS.items() if k != key}})

    async def read(self, key, host):
        if key not in config.NANOLEAF_TOKENS:
            raise RuntimeError("not paired")
        res = await self.http.get(self._url(key))
        res.raise_for_status()
        info = res.json()
        return Device(id=f"nanoleaf:{key}", source=self.source, name=str(info.get("name") or "Nanoleaf"),
                      model=info.get("model"), manufacturer=self.manufacturer,
                      entities={"light": light_entity(info.get("state") or {})})

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        key = device.id.split(":", 1)[1]
        body: dict = {}
        if toggle:
            on = not entity.state
        if on is not None:
            body["on"] = {"value": on}
        if brightness is not None:
            body["on"] = {"value": True}
            body["brightness"] = {"value": brightness}
        if "color_temp" in extra:
            body["on"] = {"value": True}
            body["ct"] = {"value": extra["color_temp"]}
        if "color" in extra:
            body["on"] = {"value": True}
            body["hue"] = {"value": round(extra["color"]["h"]) % 360}
            body["sat"] = {"value": round(extra["color"]["s"])}
        res = await self.http.put(self._url(key, "/state"), json=body)
        res.raise_for_status()
