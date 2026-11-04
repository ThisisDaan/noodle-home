"""Phones running the Noodle app. The app pushes battery, charging and location; this adapter turns that into a
device with a battery sensor, a charging sensor and a "home" presence sensor (usable in flows like any other)."""

from __future__ import annotations

import math
import time

from .. import config
from ..hub import Device, Entity, Hub

HOME_RADIUS = 150.0  # metres from the home position (HOMEPI_LAT / HOMEPI_LON) that count as home
MAX_ACCURACY = 500.0  # a fix worse than this says nothing about being home, so the old state stays


def _distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


class PhoneAdapter:
    source = "phone"

    def __init__(self, hub: Hub) -> None:
        self.hub = hub

    async def run(self) -> None:
        pass  # phones push; there is nothing to connect to

    async def command(self, device: Device, entity: Entity, on, brightness, toggle) -> None:
        raise ValueError("a phone cannot be controlled")

    def report(self, phone_id: str, name: str, battery: int | None, charging: bool | None,
               latitude: float | None, longitude: float | None, accuracy: float | None) -> bool | None:
        """Update the phone's device. Returns whether it is home (None = unknown)."""
        device_id = f"phone:{phone_id}"
        old = self.hub.devices.get(device_id)
        home = old.entities["home"].state if old else None
        if latitude is not None and longitude is not None and (accuracy is None or accuracy <= MAX_ACCURACY):
            home = _distance(latitude, longitude, config.LATITUDE, config.LONGITUDE) <= HOME_RADIUS
        entities = {
            "home": Entity("home", "binary_sensor", "Home", state=home, device_class="presence"),
            "charging": Entity("charging", "binary_sensor", "Charging",
                               state=charging if charging is not None else (old.entities["charging"].state if old else None),
                               device_class="battery_charging"),
            "battery": Entity("battery", "sensor", "Battery", state=battery, unit="%", device_class="battery"),
        }
        device = Device(id=device_id, source=self.source, name=name, model="Noodle app", manufacturer="Android",
                        battery=battery, last_seen=time.time(), entities=entities)
        self.hub.upsert(device)
        return home
