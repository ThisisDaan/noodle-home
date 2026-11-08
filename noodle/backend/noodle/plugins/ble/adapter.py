"""Bluetooth temperature and humidity sensors, read from the advertisements they broadcast.

No pairing is needed: a passive listener on this machine's Bluetooth (BlueZ over D-Bus on Linux) hears them.
While the user has pressed Search it also keeps a list of what is nearby, so the sensors can be added.

Supported, each by its own decoder below (add one function and an entry in DECODERS for a new brand):
- Xiaomi sensors that send unencrypted MiBeacon frames (LYWSDCGQ and similar)
- Xiaomi LYWSD03MMC and clones running the custom ATC / pvvx firmware
- Govee H5072, H5074, H5075 and the like
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from ... import config
from ...hub import Device, Entity, Hub

log = logging.getLogger(__name__)

MIBEACON_UUID = "0000fe95-0000-1000-8000-00805f9b34fb"
ENV_SENSING_UUID = "0000181a-0000-1000-8000-00805f9b34fb"  # used by the ATC and pvvx firmware
GOVEE_COMPANY = 0xEC88
SILENT_AFTER = 30 * 60  # seconds without a temperature report before the sensor counts as offline
NEARBY_FOR = 90  # seconds a device stays in the nearby list after it was last heard


def parse_mibeacon(data: bytes) -> dict:
    """Decode the object in an unencrypted MiBeacon frame into temperature/humidity/battery."""
    if len(data) < 5:
        return {}
    frame = int.from_bytes(data[0:2], "little")
    if frame & 0x08 or not frame & 0x40:  # encrypted, or no object in this frame
        return {}
    i = 5
    if frame & 0x10:
        i += 6  # MAC address
    if frame & 0x20:
        i += 1  # capability byte
    if len(data) < i + 3:
        return {}
    obj, size = int.from_bytes(data[i:i + 2], "little"), data[i + 2]
    payload = data[i + 3:i + 3 + size]
    out: dict = {}
    if obj == 0x100D and len(payload) >= 4:
        out["temperature"] = int.from_bytes(payload[0:2], "little", signed=True) / 10
        out["humidity"] = int.from_bytes(payload[2:4], "little") / 10
    elif obj == 0x1004 and len(payload) >= 2:
        out["temperature"] = int.from_bytes(payload[0:2], "little", signed=True) / 10
    elif obj == 0x1006 and len(payload) >= 2:
        out["humidity"] = int.from_bytes(payload[0:2], "little") / 10
    elif obj == 0x100A and payload:
        out["battery"] = payload[0]
    return out


def parse_atc(data: bytes) -> dict:
    """LYWSD03MMC with custom firmware: the ATC1441 format (13 bytes) or the pvvx format (15 bytes)."""
    if len(data) == 13:  # MAC (6), temperature x10 (big endian), humidity, battery %, millivolt, counter
        return {"temperature": int.from_bytes(data[6:8], "big", signed=True) / 10, "humidity": data[8], "battery": data[9]}
    if len(data) >= 15:  # MAC (6), temperature x100, humidity x100 (little endian), millivolt, battery %
        return {"temperature": int.from_bytes(data[6:8], "little", signed=True) / 100,
                "humidity": int.from_bytes(data[8:10], "little") / 100, "battery": data[12]}
    return {}


def parse_govee(data: bytes) -> dict:
    if len(data) == 6:  # H5072, H5075 and similar: temperature and humidity packed in one number
        value = int.from_bytes(data[1:4], "big")
        negative = bool(value & 0x800000)
        value &= 0x7FFFFF
        return {"temperature": (-1 if negative else 1) * (value // 1000) / 10, "humidity": (value % 1000) / 10, "battery": data[4]}
    if len(data) == 7:  # H5074
        return {"temperature": int.from_bytes(data[1:3], "little", signed=True) / 100,
                "humidity": int.from_bytes(data[3:5], "little") / 100, "battery": data[5]}
    return {}


# Each decoder looks at an advertisement and returns (what it is, maker, readings), or None if it is not its kind.
Decoder = Callable[[object], "tuple[str, str, dict] | None"]


def _mibeacon(adv) -> tuple[str, str, dict] | None:
    data = adv.service_data.get(MIBEACON_UUID)
    if data is None:
        return None
    return "Xiaomi thermometer", "Xiaomi", parse_mibeacon(data)


def _atc(adv) -> tuple[str, str, dict] | None:
    data = adv.service_data.get(ENV_SENSING_UUID)
    values = parse_atc(data) if data else {}
    return ("Xiaomi thermometer (custom firmware)", "Xiaomi", values) if values else None


def _govee(adv) -> tuple[str, str, dict] | None:
    data = adv.manufacturer_data.get(GOVEE_COMPANY)
    values = parse_govee(data) if data else {}
    return ("Govee thermometer", "Govee", values) if values else None


DECODERS: list[Decoder] = [_mibeacon, _atc, _govee]


def decode(adv) -> tuple[str, str, dict] | None:
    for decoder in DECODERS:
        if found := decoder(adv):
            return found
    return None


def _clean(name: str) -> str:
    """Names are saved as MAC=Name,MAC=Name, so those two characters cannot be in a name."""
    return name.replace(",", " ").replace("=", " ").strip()


class BleAdapter:
    source = "ble"

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.sensors: dict[str, str] = {}
        self.last_temperature: dict[str, float] = {}
        self.scanning = False
        self.error: str | None = None
        # address -> what was last heard: name, rssi, kind (None = not a sensor we can read), time
        self.nearby: dict[str, dict] = {}
        self.searching = False  # what is nearby is only recorded while the user has pressed Search

    @staticmethod
    def _id(mac: str) -> str:
        return f"ble:{mac}"

    async def run(self) -> None:
        self.sensors = {mac.upper(): name for mac, name in config.BLE_SENSORS.items()}
        for mac, name in self.sensors.items():
            self.hub.upsert(Device(id=self._id(mac), source=self.source, name=name, model="Bluetooth sensor",
                                   available=False, entities={
                                       "temperature": Entity("temperature", "sensor", "Temperature", unit="°C",
                                                             device_class="temperature"),
                                       "humidity": Entity("humidity", "sensor", "Humidity", unit="%",
                                                          device_class="humidity")}))
        # A sensor that was removed disappears from the hub.
        for device_id in [d for d, dev in self.hub.devices.items() if dev.source == self.source
                          and dev.id.split(":", 1)[1] not in self.sensors]:
            self.hub.remove(device_id)
        silence = asyncio.create_task(self._watch_silence())
        try:
            from bleak import BleakScanner  # imported here so the app still runs without Bluetooth

            while True:
                try:
                    async with BleakScanner(detection_callback=self._seen):
                        self.scanning, self.error = True, None
                        log.info("listening for Bluetooth sensors (%d added)", len(self.sensors))
                        while True:
                            await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    self.error = str(err) or type(err).__name__
                    log.warning("Bluetooth scanner stopped (%s), retrying in 30s", self.error)
                finally:
                    self.scanning = False
                await asyncio.sleep(30)
        finally:
            silence.cancel()

    def _seen(self, ble_device, advertisement) -> None:
        mac = ble_device.address.upper()
        found = decode(advertisement)
        if self.searching:
            self.nearby[mac] = {"address": mac, "name": advertisement.local_name or ble_device.name or "",
                                "rssi": advertisement.rssi, "kind": found[0] if found else None,
                                "time": time.time()}
        if mac not in self.sensors or not found:
            return
        kind, maker, values = found
        device = self.hub.devices.get(self._id(mac))
        if not values or not device:
            return
        device.model, device.manufacturer = kind, maker
        for key in ("temperature", "humidity"):
            if key in values:
                device.entities[key].state = values[key]
        if "battery" in values:
            device.battery = values["battery"]
        if "temperature" in values:
            self.last_temperature[mac] = time.time()
            device.available = True
        self.hub.changed(device)

    def list_nearby(self) -> list[dict]:
        now = time.time()
        for mac in [m for m, d in self.nearby.items() if now - d["time"] > NEARBY_FOR]:
            del self.nearby[mac]
        rows = [{**d, "added": d["address"] in self.sensors, "seconds_ago": round(now - d["time"])} for d in self.nearby.values()]
        for row in rows:
            row.pop("time")
        return sorted(rows, key=lambda r: (r["kind"] is None, -(r["rssi"] or -200)))

    async def search(self, seconds: float, found) -> None:
        """Report the sensors heard during `seconds`. The listener runs anyway; this only lists what it hears."""
        if self.error:
            raise RuntimeError(f"Bluetooth is not available on this machine: {self.error}")
        reported: set[str] = set()
        self.nearby.clear()
        self.searching = True
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                for d in self.list_nearby():
                    if d["kind"] and not d["added"] and d["address"] not in reported:
                        reported.add(d["address"])
                        found(d["address"], name=d["name"] or d["kind"], detail=f"{d['kind']} · {d['address']}")
                await asyncio.sleep(1)
        finally:
            self.searching = False  # the list stays for adding what was found, and stops growing

    def sensor_list(self) -> list[dict]:
        out = []
        for mac, name in self.sensors.items():
            device = self.hub.devices.get(self._id(mac))
            out.append({"address": mac, "name": name, "model": device.model if device else None,
                        "available": bool(device and device.available)})
        return out

    @staticmethod
    def pairs_after(current: dict[str, str], address: str, name: str | None) -> str:
        """The BLE_SENSORS setting with a sensor added, renamed (name given) or removed (name None)."""
        pairs = {k.upper(): v for k, v in current.items()}
        if name is None:
            pairs.pop(address.upper(), None)
        else:
            pairs[address.upper()] = _clean(name) or address.upper()
        return ",".join(f"{k}={v}" for k, v in pairs.items())

    async def _watch_silence(self) -> None:
        while True:
            await asyncio.sleep(60)
            for mac in self.sensors:
                device = self.hub.devices.get(self._id(mac))
                silent = time.time() - self.last_temperature.get(mac, 0) > SILENT_AFTER
                if device and device.available and silent:
                    device.available = False
                    self.hub.changed(device)

    async def command(self, *_args) -> None:
        raise ValueError("Bluetooth sensors cannot be controlled")
