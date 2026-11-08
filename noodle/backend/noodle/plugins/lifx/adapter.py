"""LIFX bulbs over the local network (the LIFX LAN protocol, UDP port 56700). No cloud, no account, no bridge.

Nothing searches in the background. The user starts a search (Integrations page), bulbs that answer are listed,
and the ones they add are saved with their address (setting lifx_bulbs). After that each bulb is asked for its
state every few seconds, since bulbs do not push changes. Only if a saved bulb stops answering (it may have a new
address) is one broadcast sent now and then to find it again, until it answers.

Every bulb is treated as a colour bulb with a white range of 1500-9000 K. White-only models ignore the colour
commands. (Telling models apart needs LIFX's product table; add it here when it matters.)
"""

from __future__ import annotations

import asyncio
import logging
import random
import struct
import time
from dataclasses import dataclass, field

from ... import config
from ...hub import Device, Entity, Hub

log = logging.getLogger(__name__)

PORT = 56700
HEADER = 36
MIN_KELVIN, MAX_KELVIN, DEFAULT_KELVIN = 1500, 9000, 3500
POLL_EVERY = 8  # seconds between state requests to the bulbs the user added
SEARCH_PACKET_EVERY = 2  # during a search the user started
GONE_AFTER = 30  # seconds without an answer before a bulb counts as offline
FADE_MS = 250

GET_SERVICE, STATE_SERVICE = 2, 3
GET_COLOR, SET_COLOR, LIGHT_STATE = 101, 102, 107
SET_LIGHT_POWER = 117
FULL = 65535


def build(msg_type: int, payload: bytes = b"", *, source: int, target: bytes = b"\0" * 8, seq: int = 0,
          tagged: bool = False, res_required: bool = False) -> bytes:
    """One LIFX packet: a 36 byte header and the payload."""
    frame = 1024 | (1 << 12) | (int(tagged) << 13)  # protocol 1024, addressable, tagged only for discovery
    flags = int(res_required)
    return struct.pack("<HHI8s6sBBQHH", HEADER + len(payload), frame, source, target, b"", flags, seq & 0xFF, 0,
                       msg_type, 0) + payload


def parse(data: bytes) -> tuple[int, str, bytes] | None:
    """(message type, the bulb's address as 12 hex digits, payload), or None if it is not a LIFX packet."""
    if len(data) < HEADER:
        return None
    size, _frame, _source, target, _r, _flags, _seq, _r2, msg_type, _r3 = struct.unpack("<HHI8s6sBBQHH", data[:HEADER])
    if size != len(data):
        return None
    return msg_type, target[:6].hex(), data[HEADER:]


def set_color(hue: int, sat: int, bri: int, kelvin: int, ms: int = FADE_MS) -> bytes:
    return struct.pack("<BHHHHI", 0, hue, sat, bri, kelvin, ms)


def set_power(on: bool, ms: int = 0) -> bytes:
    return struct.pack("<HI", FULL if on else 0, ms)


def read_state(payload: bytes) -> dict | None:
    if len(payload) < 52:
        return None
    hue, sat, bri, kelvin, _r, power = struct.unpack("<HHHHhH", payload[:12])
    label = payload[12:44].split(b"\0", 1)[0].decode("utf-8", "replace")
    return {"hsbk": (hue, sat, bri, kelvin), "power": power > 0, "label": label}


@dataclass
class Bulb:
    mac: str
    addr: tuple[str, int]
    label: str = ""
    hsbk: tuple[int, int, int, int] = (0, 0, FULL, DEFAULT_KELVIN)
    power: bool = False
    heard: float = 0.0
    seq: int = field(default=0)

    @property
    def device_id(self) -> str:
        return f"lifx:{self.mac}"


class _Protocol:
    """The asyncio side of the UDP socket; hands every datagram to the adapter."""

    def __init__(self, on_packet) -> None:
        self.on_packet = on_packet
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            self.on_packet(data, addr)
        except Exception:
            log.exception("bad LIFX packet from %s", addr)

    def error_received(self, exc) -> None:
        log.debug("LIFX socket error: %s", exc)

    def connection_lost(self, exc) -> None:
        pass


class LifxAdapter:
    source = "lifx"
    extra_commands = frozenset({"color_temp", "color"})

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.bulbs: dict[str, Bulb] = {}  # the bulbs the user added, by device id
        self.nearby: dict[str, Bulb] = {}  # answered a search but not added, by device id
        self.client = random.getrandbits(32) or 1  # tells our packets' answers from other apps' on the network
        self._protocol: _Protocol | None = None
        self._found = None  # while a search runs: where to report what answers
        self.running = False

    # --- connection

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        protocol = _Protocol(self._packet)
        try:
            await loop.create_datagram_endpoint(lambda: protocol, local_addr=("0.0.0.0", 0), allow_broadcast=True)
        except OSError as err:
            log.warning("LIFX: cannot open a UDP socket (%s)", err)
            return
        self._protocol, self.running = protocol, True
        self.bulbs = {b.device_id: b for b in (Bulb(mac, (ip, PORT)) for mac, ip in config.LIFX_BULBS.items())}
        log.info("LIFX: %d saved bulb(s)", len(self.bulbs))
        try:
            while True:
                now = time.time()
                for bulb in list(self.bulbs.values()):
                    self._send(bulb, GET_COLOR, res_required=True)
                self._check_gone(now)  # a bulb that moved to a new address is found again with Search, never on its own
                await asyncio.sleep(POLL_EVERY)
        finally:
            self.running = False
            if protocol.transport:
                protocol.transport.close()
            self._protocol = None

    def _broadcast(self) -> None:
        packet = build(GET_SERVICE, source=self.client, tagged=True, res_required=True)
        for host in ["255.255.255.255", *config.LIFX_HOSTS]:
            self._sendto(packet, (host, PORT))

    def _sendto(self, packet: bytes, addr: tuple[str, int]) -> None:
        if self._protocol and self._protocol.transport:
            try:
                self._protocol.transport.sendto(packet, addr)
            except OSError as err:
                log.debug("LIFX send to %s failed: %s", addr, err)

    def _send(self, bulb: Bulb, msg_type: int, payload: bytes = b"", res_required: bool = False) -> None:
        bulb.seq = (bulb.seq + 1) & 0xFF
        target = bytes.fromhex(bulb.mac) + b"\0\0"
        self._sendto(build(msg_type, payload, source=self.client, target=target, seq=bulb.seq,
                           res_required=res_required), bulb.addr)

    # --- searching, only while the user has asked for it

    async def search(self, seconds: float, found) -> None:
        if not self.running:
            raise RuntimeError("LIFX is not running")
        self.nearby.clear()
        self._found = found
        try:
            deadline = time.time() + seconds
            while time.time() < deadline:
                self._broadcast()
                await asyncio.sleep(SEARCH_PACKET_EVERY)
        finally:
            self._found = None

    async def add_found(self, key: str) -> None:
        self.add_bulb(key)

    def add_bulb(self, mac: str) -> None:
        """Keep a bulb the search found: save its address and start following it."""
        bulb = self.nearby.pop(f"lifx:{mac}", None)
        if bulb is None:
            raise KeyError("That bulb is no longer in the list; search again")
        self.bulbs[bulb.device_id] = bulb
        config.save({"lifx_bulbs": {**config.LIFX_BULBS, mac: bulb.addr[0]}})
        if bulb.heard:
            self._publish(bulb)

    def forget(self, mac: str) -> None:
        self.bulbs.pop(f"lifx:{mac}", None)
        self.hub.remove(f"lifx:{mac}")
        config.save({"lifx_bulbs": {k: v for k, v in config.LIFX_BULBS.items() if k != mac}})

    def bulb_list(self) -> list[dict]:
        out = []
        for bulb in self.bulbs.values():
            device = self.hub.devices.get(bulb.device_id)
            out.append({"mac": bulb.mac, "name": bulb.label or f"LIFX {bulb.mac[-4:]}", "address": bulb.addr[0],
                        "available": bool(device and device.available)})
        return out

    # --- incoming

    def _packet(self, data: bytes, addr) -> None:
        packet = parse(data)
        if packet is None:
            return
        msg_type, mac, payload = packet
        device_id = f"lifx:{mac}"
        if msg_type == STATE_SERVICE and len(payload) >= 5:
            service, port = struct.unpack("<BI", payload[:5])
            if service == 1:  # UDP
                self._answered(mac, (addr[0], port or PORT))
        elif msg_type == LIGHT_STATE:
            state = read_state(payload)
            bulb = self.bulbs.get(device_id) or self.nearby.get(device_id)
            if state is None or bulb is None:
                return
            bulb.hsbk, bulb.power, bulb.heard = state["hsbk"], state["power"], time.time()
            bulb.label = state["label"] or bulb.label
            bulb.addr = (addr[0], bulb.addr[1])
            if device_id in self.bulbs:
                self._publish(bulb)
            elif self._found:
                self._found(mac, name=bulb.label or "LIFX bulb", detail=addr[0])

    def _answered(self, mac: str, addr: tuple[str, int]) -> None:
        device_id = f"lifx:{mac}"
        if bulb := self.bulbs.get(device_id):
            if bulb.addr != addr:  # it has a new address: remember it
                bulb.addr = addr
                config.save({"lifx_bulbs": {**config.LIFX_BULBS, mac: addr[0]}})
            self._send(bulb, GET_COLOR, res_required=True)
        elif self._found:  # not added yet: only noticed while the user is searching
            bulb = self.nearby.get(device_id)
            if bulb is None:
                bulb = self.nearby[device_id] = Bulb(mac, addr)
                self._found(mac, name="LIFX bulb", detail=addr[0])
            self._send(bulb, GET_COLOR, res_required=True)  # the answer has its name

    def _check_gone(self, now: float) -> bool:
        """Mark bulbs that stopped answering as offline. True if any saved bulb is not answering."""
        lost = False
        for bulb in self.bulbs.values():
            if now - bulb.heard > GONE_AFTER:
                lost = True
                device = self.hub.devices.get(bulb.device_id)
                if device and device.available:
                    device.available = False
                    self.hub.changed(device)
        return lost

    # --- what the hub sees

    def _publish(self, bulb: Bulb) -> None:
        hue, sat, bri, kelvin = bulb.hsbk
        attrs = {"can": ["color_temp", "color"], "color_temp_range": [MIN_KELVIN, MAX_KELVIN],
                 "color_temp": kelvin, "color": {"h": round(hue / FULL * 360, 1), "s": round(sat / FULL * 100, 1)}}
        device = self.hub.devices.get(bulb.device_id)
        if device is None:
            device = Device(id=bulb.device_id, source=self.source, name=bulb.label or f"LIFX {bulb.mac[-4:]}",
                            manufacturer="LIFX", entities={"light": Entity("light", "light", "Light")})
        device.available = True
        light = device.entities["light"]
        light.state, light.brightness, light.attrs = bulb.power, round(bri / FULL * 100), attrs
        device.last_seen = bulb.heard or time.time()
        if bulb.device_id in self.hub.devices:
            self.hub.changed(device)
        else:
            self.hub.upsert(device)

    # --- control

    async def command(self, device: Device, entity: Entity, on: bool | None, brightness: int | None, toggle: bool,
                      **extra) -> None:
        bulb = self.bulbs.get(device.id)
        if bulb is None or not self.running:
            raise RuntimeError("LIFX bulb not reachable")
        hue, sat, bri, kelvin = bulb.hsbk
        recolour = False
        if "color" in extra:
            hue, sat = round(extra["color"]["h"] / 360 * FULL) % 65536, round(extra["color"]["s"] / 100 * FULL)
            recolour = True
        if "color_temp" in extra:
            hue, sat, recolour = 0, 0, True
            kelvin = max(MIN_KELVIN, min(MAX_KELVIN, extra["color_temp"]))
        if brightness is not None:
            bri, recolour = max(1, round(brightness / 100 * FULL)), True
        elif recolour and bri == 0:
            bri = FULL
        want = (not bulb.power) if toggle else on
        if want is None and recolour:
            want = True
        if recolour:
            self._send(bulb, SET_COLOR, set_color(hue, sat, bri, kelvin))
        if want is not None:
            self._send(bulb, SET_LIGHT_POWER, set_power(want))
        bulb.hsbk = (hue, sat, bri, kelvin)
        if want is not None:
            bulb.power = want
        self._publish(bulb)  # show the change now; the next answer from the bulb confirms it
        self._send(bulb, GET_COLOR, res_required=True)
