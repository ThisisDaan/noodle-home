"""IKEA DIRIGERA hub over its local API (HTTPS, port 8443). No cloud.

Pairing: the hub gives a code, you press its action button, and the hub then hands over a token. Lights, outlets,
blinds and sensors are supported. IKEA remotes and shortcut buttons are not (their presses only arrive over a
live connection).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import string
import time

import httpx

from .. import config
from ..hub import Device, Entity, Hub

log = logging.getLogger(__name__)

POLL_EVERY = 6.0
PORT = 8443


def challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def entities_from(item: dict) -> dict[str, Entity]:
    """The entities of one DIRIGERA device (an item of /v1/devices)."""
    kind, a = item.get("deviceType"), item.get("attributes") or {}
    out: dict[str, Entity] = {}
    if kind == "light":
        can = []
        attrs: dict = {}
        if "colorTemperature" in a:
            can.append("color_temp")
            attrs["color_temp"] = a["colorTemperature"]
            lo, hi = sorted((a.get("colorTemperatureMin", 2202), a.get("colorTemperatureMax", 4000)))
            attrs["color_temp_range"] = [lo, hi]
        if "colorHue" in a:
            can.append("color")
            attrs["color"] = {"h": a["colorHue"], "s": round(a.get("colorSaturation", 0) * 100, 1)}
        attrs["can"] = can
        out["light"] = Entity("light", "light", "Light", state=bool(a.get("isOn")), brightness=a.get("lightLevel"), attrs=attrs)
    elif kind == "outlet":
        out["switch"] = Entity("switch", "switch", "Outlet", state=bool(a.get("isOn")))
        if isinstance(a.get("currentActivePower"), (int, float)):
            out["power"] = Entity("power", "sensor", "Power", state=a["currentActivePower"], unit="W", device_class="power")
    elif kind == "environmentSensor":
        for key, name, field, unit, cls in (("temperature", "Temperature", "currentTemperature", "°C", "temperature"),
                                            ("humidity", "Humidity", "currentRH", "%", "humidity"),
                                            ("pm25", "PM2.5", "currentPM25", "µg/m³", "pm25")):
            if isinstance(a.get(field), (int, float)):
                out[key] = Entity(key, "sensor", name, state=a[field], unit=unit, device_class=cls)
    elif kind == "motionSensor":
        out["motion"] = Entity("motion", "binary_sensor", "Motion", state=bool(a.get("isDetected")), device_class="motion")
    elif kind == "openCloseSensor":
        out["contact"] = Entity("contact", "binary_sensor", "Open", state=bool(a.get("isOpen")), device_class="door")
    elif kind == "blinds":
        level = a.get("blindsCurrentLevel")  # 0 = open, 100 = closed; the hub's cover position is the other way round
        position = None if level is None else 100 - level
        out["cover"] = Entity("cover", "cover", "Blind", state="open" if (position or 0) > 0 else "closed",
                              attrs={"position": position} if position is not None else {})
    if isinstance(a.get("batteryPercentage"), (int, float)) and out:
        out["battery_level"] = Entity("battery_level", "sensor", "Battery", state=a["batteryPercentage"], unit="%", device_class="battery")
    return out


class DirigeraAdapter:
    source = "dirigera"
    extra_commands = frozenset({"color_temp", "color", "position", "action"})

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.http: httpx.AsyncClient | None = None
        self.connected = False
        self.error: str | None = None
        self.last: float = 0.0
        self._pairing: tuple[str, str, str] | None = None  # host, code, verifier

    def _url(self, path: str, host: str | None = None) -> str:
        return f"https://{host or config.DIRIGERA_HOST}:{PORT}{path}"

    @property
    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {config.DIRIGERA_TOKEN}"}

    async def run(self) -> None:
        self.http = httpx.AsyncClient(timeout=8, verify=False)
        try:
            while True:
                if config.DIRIGERA_HOST and config.DIRIGERA_TOKEN:
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
        res = await self.http.get(self._url("/v1/devices"), headers=self._auth)
        res.raise_for_status()
        now = time.time()
        for item in res.json():
            entities = entities_from(item)
            if not entities:
                continue
            device_id = f"dirigera:{item['id']}"
            attrs = item.get("attributes") or {}
            device = self.hub.devices.get(device_id)
            if device is None:
                device = Device(id=device_id, source=self.source, name=str(attrs.get("customName") or attrs.get("model") or item["id"]),
                                model=attrs.get("model"), manufacturer=attrs.get("manufacturer") or "IKEA", entities=entities)
                device.available, device.last_seen = bool(item.get("isReachable", True)), now
                self.hub.upsert(device)
                continue
            for key, e in entities.items():
                old = device.entities.get(key)
                if old is None:
                    device.entities[key] = e
                else:
                    old.state, old.brightness, old.attrs = e.state, e.brightness, e.attrs
            device.available, device.last_seen = bool(item.get("isReachable", True)), now
            self.hub.changed(device)

    # --- pairing: the user presses the hub's action button

    async def pair(self, host: str) -> bool:
        """Start pairing, or finish it when the button was pressed. True when paired, False while waiting."""
        if self.http is None:
            raise RuntimeError("IKEA DIRIGERA is not running")
        host = host.strip().removeprefix("https://").removeprefix("http://").rstrip("/").split(":")[0]
        if not host:
            raise ValueError("Enter the IP address of the hub (see your router or the IKEA Home smart app)")
        try:
            if self._pairing is None or self._pairing[0] != host:
                verifier = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(128))
                res = await self.http.get(self._url("/v1/oauth/authorize", host), params={
                    "audience": "homesmart.local", "response_type": "code", "code_challenge": challenge(verifier),
                    "code_challenge_method": "S256"})
                res.raise_for_status()
                self._pairing = (host, res.json()["code"], verifier)
                return False
            _, code, verifier = self._pairing
            res = await self.http.post(self._url("/v1/oauth/token", host), data={
                "code": code, "name": "Noodle", "grant_type": "authorization_code", "code_verifier": verifier})
        except (httpx.HTTPError, OSError) as err:
            self._pairing = None
            raise ValueError(f"Nothing answered at {host} ({err.__class__.__name__})") from err
        if res.status_code in (401, 403, 404, 408):
            return False  # the button has not been pressed yet
        res.raise_for_status()
        config.save({"dirigera_host": host, "dirigera_token": res.json()["access_token"]})
        self._pairing = None
        return True

    # --- control

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool,
                      **extra) -> None:
        if not self.connected or self.http is None:
            raise RuntimeError("The IKEA hub is not reachable")
        attrs: dict = {}
        if entity.kind in ("light", "switch"):
            want = (not entity.state) if toggle else on
            if brightness is not None:
                want = True
                attrs["lightLevel"] = max(1, brightness)
            if "color_temp" in extra:
                want = True
                attrs["colorTemperature"] = extra["color_temp"]
            if "color" in extra:
                want = True
                attrs.update(colorHue=round(extra["color"]["h"]) % 360, colorSaturation=round(extra["color"]["s"]) / 100)
            if want is not None:
                attrs["isOn"] = want
        elif entity.kind == "cover":
            if "position" in extra:
                attrs["blindsTargetLevel"] = 100 - round(extra["position"])
            elif extra.get("action") in ("open", "close"):
                attrs["blindsTargetLevel"] = 0 if extra["action"] == "open" else 100
            else:
                raise ValueError("This blind cannot be stopped from here")
        if not attrs:
            return
        res = await self.http.patch(self._url(f"/v1/devices/{device.id.split(':', 1)[1]}"), headers=self._auth,
                                    json=[{"attributes": attrs}])
        res.raise_for_status()
        await self.refresh()
