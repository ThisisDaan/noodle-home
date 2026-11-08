"""Shelly relays, plugs, dimmers and lights over their local HTTP API. No cloud.

Both generations are supported: Gen1 (/status, /relay/0?turn=on, /light/0) and Gen2 and newer (Plus, Pro, Mini:
/rpc/Shelly.GetStatus, /rpc/Switch.Set, /rpc/Light.Set). A device that measures power also gets a power sensor.
"""

from __future__ import annotations

from ...hub import Device, Entity
from ..lan.adapter import LanAdapter


def _entity_key(prefix: str, index: int, count: int) -> tuple[str, str]:
    """('switch', 'Switch') for a device with one, ('switch_2', 'Switch 2') for one with several."""
    return (prefix if count == 1 else f"{prefix}_{index + 1}", prefix.capitalize() if count == 1 else f"{prefix.capitalize()} {index + 1}")


def entities_gen1(status: dict) -> dict[str, Entity]:
    out: dict[str, Entity] = {}
    relays = status.get("relays") or []
    for i, relay in enumerate(relays):
        key, name = _entity_key("switch", i, len(relays))
        out[key] = Entity(key, "switch", name, state=bool(relay.get("ison")))
    lights = status.get("lights") or []
    for i, light in enumerate(lights):
        key, name = _entity_key("light", i, len(lights))
        out[key] = Entity(key, "light", name, state=bool(light.get("ison")), brightness=light.get("brightness"))
    meters = [m.get("power") for m in status.get("meters") or [] if isinstance(m.get("power"), (int, float))]
    if meters:
        out["power"] = Entity("power", "sensor", "Power", state=round(sum(meters), 1), unit="W", device_class="power")
    if isinstance(status.get("temperature"), (int, float)):
        out["temperature"] = Entity("temperature", "sensor", "Temperature", state=round(status["temperature"], 1),
                                    unit="°C", device_class="temperature")
    return out


def entities_gen2(status: dict) -> dict[str, Entity]:
    out: dict[str, Entity] = {}
    switches = sorted(k for k in status if k.startswith("switch:"))
    lights = sorted(k for k in status if k.startswith("light:"))
    watts = []
    for i, k in enumerate(switches):
        key, name = _entity_key("switch", i, len(switches))
        out[key] = Entity(key, "switch", name, state=bool(status[k].get("output")))
        if isinstance(status[k].get("apower"), (int, float)):
            watts.append(status[k]["apower"])
    for i, k in enumerate(lights):
        key, name = _entity_key("light", i, len(lights))
        out[key] = Entity(key, "light", name, state=bool(status[k].get("output")), brightness=status[k].get("brightness"))
        if isinstance(status[k].get("apower"), (int, float)):
            watts.append(status[k]["apower"])
    if watts:
        out["power"] = Entity("power", "sensor", "Power", state=round(sum(watts), 1), unit="W", device_class="power")
    temp = (status.get("sys") or {}).get("temperature") or status.get("temperature:0", {}).get("tC")
    if isinstance(temp, (int, float)):
        out["temperature"] = Entity("temperature", "sensor", "Temperature", state=round(temp, 1), unit="°C",
                                    device_class="temperature")
    return out


class ShellyAdapter(LanAdapter):
    source = "shelly"
    manufacturer = "Shelly"
    setting, attr = "shelly_devices", "SHELLY_DEVICES"
    mdns = ("_shelly._tcp.local.", "_http._tcp.local.")

    def __init__(self, hub) -> None:
        super().__init__(hub)
        self.info: dict[str, dict] = {}

    async def _about(self, host: str) -> dict:
        res = await self.http.get(f"http://{host}/shelly")
        res.raise_for_status()
        data = res.json()
        if not isinstance(data, dict) or "mac" not in data:
            raise ValueError("not a Shelly")
        return data

    async def identify(self, host):
        about = await self._about(host)
        key = str(about["mac"]).lower().replace(":", "")
        return key, str(about.get("name") or about.get("id") or f"Shelly {key[-4:]}")

    async def read(self, key, host):
        if key not in self.info:
            about = await self._about(host)
            self.info[key] = {"gen": int(about.get("gen") or 1), "model": about.get("model") or about.get("type"),
                              "name": about.get("name") or about.get("id")}
        info = self.info[key]
        if info["gen"] >= 2:
            res = await self.http.get(f"http://{host}/rpc/Shelly.GetStatus")
            res.raise_for_status()
            entities = entities_gen2(res.json())
        else:
            res = await self.http.get(f"http://{host}/status")
            res.raise_for_status()
            entities = entities_gen1(res.json())
        return Device(id=f"shelly:{key}", source=self.source, name=info["name"] or f"Shelly {key[-4:]}",
                      model=info["model"], manufacturer=self.manufacturer, entities=entities)

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        key = device.id.split(":", 1)[1]
        gen = self.info.get(key, {}).get("gen", 1)
        last = entity.key.rsplit("_", 1)[-1]
        index = int(last) - 1 if "_" in entity.key and last.isdigit() else 0
        kind = entity.kind  # switch or light
        if gen >= 2:
            method = "Switch.Set" if kind == "switch" else "Light.Set"
            params = {"id": index}
            if toggle:
                method = method.replace(".Set", ".Toggle")
            else:
                if on is not None:
                    params["on"] = str(on).lower()
                if brightness is not None:
                    params["brightness"] = brightness
                    params.setdefault("on", "true")
            res = await self.http.get(f"http://{host}/rpc/{method}", params=params)
        else:
            path = f"/relay/{index}" if kind == "switch" else f"/light/{index}"
            params = {}
            if toggle:
                params["turn"] = "toggle"
            else:
                if on is not None:
                    params["turn"] = "on" if on else "off"
                if brightness is not None:
                    params["brightness"] = brightness
                    params["turn"] = "on"
            res = await self.http.get(f"http://{host}{path}", params=params)
        res.raise_for_status()
