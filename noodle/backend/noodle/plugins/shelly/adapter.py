"""Shelly relays, plugs, dimmers and lights over their local HTTP API. No cloud.

Both generations are supported: Gen1 (/status, /relay/0?turn=on, /light/0) and Gen2 and newer (Plus, Pro, Mini:
/rpc/Shelly.GetStatus, /rpc/Switch.Set, /rpc/Light.Set). A device that measures power also gets a power sensor.
Search also finds new Shellies that are not on the Wi-Fi yet and puts them on it (hotspot.py).
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Callable

from ...hub import Device, Entity
from ..lan.adapter import LanAdapter
from . import hotspot

JOIN_SECONDS = 120  # how long a newly set up Shelly gets to show up on the home network
SCAN_EVERY = 6.0  # seconds between looks at the nearby Wi-Fi networks during a search


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
        self.wifi = hotspot.system_wifi()
        self.hotspots: dict[str, dict] = {}  # Shellies a search found that are not on the Wi-Fi yet: "ap:<ssid>" -> info
        self._setting_up = asyncio.Lock()

    # --- new Shellies that are not on the Wi-Fi yet (see hotspot.py)

    async def search(self, seconds, found) -> None:
        """Shellies on the network (mDNS), and new ones still waiting on their own Wi-Fi, at the same time."""
        self.hotspots.clear()
        await asyncio.gather(super().search(seconds, found), self._search_hotspots(seconds, found))

    async def _search_hotspots(self, seconds: float, found) -> None:
        """Look at the nearby Wi-Fi networks every few seconds while the search runs (only then), because a
        Shelly that was just powered on takes a moment to open its network, and Windows lists what it last heard."""
        note = getattr(found, "note", None) or (lambda text: None)
        end = time.monotonic() + max(0.0, seconds - SCAN_EVERY)
        fresh = True
        while True:
            try:
                device = await self.wifi.device()
                networks = await self.wifi.scan(device, fresh)
                wired = await self.wifi.wired() if fresh else wired
            except hotspot.WifiError as err:
                note(f"New Shellies that are not on your Wi-Fi yet cannot be set up from here: {err}. To do it by "
                     f"hand, join the Shelly's own Wi-Fi (shelly…), open http://{hotspot.SETUP_ADDRESS} and enter "
                     "your Wi-Fi there, then search again.")
                return
            self._report_hotspots(device, networks, wired, found)
            if time.monotonic() >= end:
                break
            fresh = False
            await asyncio.sleep(SCAN_EVERY)
        if not self.hotspots and sys.platform == "win32":
            note("No new Shelly heard. Windows only lists the Wi-Fi networks it heard last: open the Wi-Fi list on "
                 "the taskbar to make it look again, then search again.")

    def _report_hotspots(self, device: str, networks: list, wired: bool, found) -> None:
        homes = [n for n in networks if not hotspot.is_shelly_ap(n.ssid)]
        homes.sort(key=lambda n: not (hotspot.is_24(n.freq) or not n.freq))  # 2.4 GHz first (stable: in use first)
        current = next((n.ssid for n in homes if n.in_use), None)
        wifi = {"networks": [n.ssid for n in homes], "current": current, "offline": bool(current) and not wired,
                # heard on 5 GHz only here: the Shelly cannot join it, unless the router has 2.4 GHz too
                "only5": [n.ssid for n in homes if n.freq and not hotspot.is_24(n.freq)]}
        for n in networks:
            if hotspot.is_shelly_ap(n.ssid):
                key = f"ap:{n.ssid}"
                self.hotspots[key] = {"ssid": n.ssid, "device": device}
                found(key, name=hotspot.ap_name(n.ssid), detail="New: not on your Wi-Fi yet", wifi=wifi)

    async def add_found(self, key: str, wifi_ssid: str | None = None, wifi_password: str = "",
                        report: Callable[[str], None] = lambda text: None) -> None:
        if not key.startswith("ap:"):
            return await super().add_found(key)
        spot = self.hotspots.get(key)
        if spot is None:
            raise KeyError("That Shelly is no longer in the list; search again")
        if not wifi_ssid:
            raise ValueError("Pick the Wi-Fi network the Shelly should join")
        if self.http is None:
            raise RuntimeError("shelly is not running")
        if self._setting_up.locked():
            raise ValueError("Another Shelly is being set up; wait until it is done")
        # Shielded: if the page loses its connection (the hub may be on the Wi-Fi it switches), the setup goes on.
        await asyncio.shield(asyncio.ensure_future(self._set_up(key, spot, wifi_ssid, wifi_password, report)))

    async def _set_up(self, key, spot, ssid, password, report) -> None:
        async with self._setting_up:
            device = spot["device"]
            try:
                back = await self.wifi.active(device)
            except hotspot.WifiError:
                back = None
            report("Joining the Shelly's own Wi-Fi…")
            try:
                await self.wifi.join(device, spot["ssid"])
                report("Giving it your Wi-Fi details…")
                mac = await hotspot.configure(self.http, ssid, password)
            except hotspot.WifiError as err:
                raise ValueError(str(err)) from err
            finally:
                report("Going back to your network…")
                await self.wifi.leave(back)
            report(f"Waiting for it to join {ssid}…")
            host = await self.wait_for(mac, JOIN_SECONDS)
            if host is None:
                raise ValueError(f"The Shelly did not show up on {ssid}. Check the password and that {ssid} is a "
                                 "2.4 GHz network, then reset the Shelly (hold its button for about 10 seconds) "
                                 "and search again.")
            report("Adding it…")
            await self.add_host(host)
            self.hotspots.pop(key, None)

    async def wait_for(self, mac: str, seconds: float) -> str | None:
        """The address of the Shelly with this key once it announces itself on the network, or None."""
        from ... import mdns

        done = asyncio.Event()
        result: dict[str, str] = {}

        async def on_service(service_type, name, info) -> None:
            for host in mdns.ipv4(info):
                if done.is_set():
                    return
                try:
                    key, _ = await self.identify(host)
                except Exception:
                    continue
                if key == mac:
                    result["host"] = host
                    done.set()

        await mdns.browse(list(self.mdns), seconds, on_service, until=done)
        return result.get("host")

    # --- reading and controlling

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
