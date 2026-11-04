"""Thermostat: drives a heater plug from a room temperature sensor (both picked in the settings).

Same behaviour as the Home Assistant generic_thermostat it replaces: heat until
target + hot tolerance, start again below target - cold tolerance, at least
MIN_CYCLE between switches, and re-send the wanted state every KEEP_ALIVE.
Safety: when the room sensor goes silent for 30 minutes while heating, the heater
and the thermostat switch off and the phone gets a notification.
"""

from __future__ import annotations

import asyncio
import logging
import time

from .. import config, notify
from ..hub import Device, Entity, Hub

log = logging.getLogger(__name__)

COLD_TOLERANCE, HOT_TOLERANCE = 0.5, 0.3
MIN_CYCLE, KEEP_ALIVE = 5 * 60, 10 * 60
MIN_TEMP, MAX_TEMP = 10.0, 24.0


class ThermostatAdapter:
    source = "thermostat"

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self._published: str | None = None  # id of the device we added to the hub
        self.mode = hub.store.get("thermostat_mode") or "off"
        self.target = float(hub.store.get("thermostat_target") or 18.0)
        self._last_sent = 0.0
        self._lock = asyncio.Lock()
        hub.on_state_change(self._changed)

    @property
    def device_id(self) -> str:
        return config.THERMOSTAT_ID

    @property
    def sensor(self) -> tuple[str, str]:
        return (config.THERMOSTAT_SENSOR_DEVICE, config.THERMOSTAT_SENSOR_KEY)

    @property
    def heater(self) -> tuple[str, str]:
        return (config.THERMOSTAT_HEATER_DEVICE, config.THERMOSTAT_HEATER_KEY)

    @property
    def configured(self) -> bool:
        return all((*self.sensor, *self.heater, self.device_id))

    def remove(self) -> None:
        """Take the thermostat device off the hub (the integration was removed or points elsewhere)."""
        if self._published:
            self.hub.remove(self._published)
            self._published = None

    def _device(self) -> Device:
        return Device(id=self.device_id, source=self.source, name=config.THERMOSTAT_NAME, model="Thermostat",
                      manufacturer="Noodle", entities={
                          "heat": Entity("heat", "switch", "Heating mode", state=self.mode == "heat"),
                          "target": Entity("target", "number", "Target", state=self.target, unit="°C"),
                          # A copy of the room sensor, shown next to the controls. No device class, so it
                          # is not offered as a second temperature sensor.
                          "temperature": Entity("temperature", "sensor", "Room", unit="°C",
                                                state=self._value(self.sensor)),
                          "heating": Entity("heating", "binary_sensor", "Heater", device_class="heat",
                                            state=self._value(self.heater)),
                      })

    def _value(self, ref: tuple[str, str]):
        device = self.hub.devices.get(ref[0])
        entity = device.entities.get(ref[1]) if device else None
        return entity.state if entity else None

    def _publish(self) -> None:
        existing = self.hub.devices.get(self.device_id)
        fresh = self._device()
        if existing:
            existing.entities = fresh.entities
            existing.name = fresh.name
            self.hub.changed(existing)
        else:
            self.hub.upsert(fresh)
        self._published = self.device_id

    async def run(self) -> None:
        if self._published != self.device_id or not self.configured:
            self.remove()  # settings changed: the old device goes away
        if not self.configured:
            return
        await asyncio.sleep(10)  # let the sensor and plug load
        self._publish()
        while True:
            await self._control("tick")
            await asyncio.sleep(30)

    def _changed(self, device: Device, entity: Entity, old, new) -> None:
        if (device.id, entity.key) in (self.sensor, self.heater) and self.device_id in self.hub.devices:
            self._publish()
            asyncio.create_task(self._control("change"))

    async def _control(self, why: str) -> None:
        if not config.AUTOMATIONS or self.device_id not in self.hub.devices:
            return
        async with self._lock:
            sensor = self.hub.devices.get(self.sensor[0])
            heater_on = self._value(self.heater)
            if self.mode != "heat":
                return
            if not sensor or not sensor.available or not isinstance(self._value(self.sensor), (int, float)):
                log.warning("room sensor silent: heater and thermostat off")
                await self._set_mode("off")
                await notify_safe("The room sensor stopped reporting a temperature. The heater has been switched off.")
                return
            temp = float(self._value(self.sensor))
            since = self.hub.since(*self.heater) or 0
            can_switch = time.time() - since >= MIN_CYCLE
            want = heater_on
            if heater_on is not True and temp <= self.target - COLD_TOLERANCE and can_switch:
                want = True
            elif heater_on is True and temp >= self.target + HOT_TOLERANCE and can_switch:
                want = False
            if want != heater_on or (want is not None and time.time() - self._last_sent >= KEEP_ALIVE):
                await self._heater(bool(want), f"{temp:.1f} °C, target {self.target:.1f} °C ({why})")

    async def _heater(self, on: bool, reason: str) -> None:
        await self.hub.command(self.heater[0], self.heater[1], on=on)
        self._last_sent = time.time()
        log.info("heater %s: %s", "on" if on else "off", reason)

    async def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self.hub.store.set("thermostat_mode", mode)
        if mode == "off" and self._value(self.heater) is not False:
            await self._heater(False, "thermostat off")
        self._publish()

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None,
                      toggle: bool, value: float | None = None) -> None:
        if entity.key == "heat":
            heat = (self.mode != "heat") if toggle else bool(on)
            await self._set_mode("heat" if heat else "off")
        elif entity.key == "target" and value is not None:
            self.target = round(min(MAX_TEMP, max(MIN_TEMP, float(value))) * 2) / 2
            self.hub.store.set("thermostat_target", str(self.target))
            self._publish()
        else:
            raise ValueError(f"{entity.key} cannot be controlled")
        await self._control("command")


async def notify_safe(message: str) -> None:
    try:
        await notify.send(message, "Heating off", "high")
    except Exception as err:
        log.warning("notification failed: %s", err)
