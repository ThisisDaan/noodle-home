"""Finding and checking the MQTT broker that Zigbee2MQTT talks through.

Used by the setup screens, and only when the user gets there or presses a button: nothing here runs in the
background. A broker is recognised by speaking MQTT to it (a CONNECT packet and the CONNACK it answers with), not
only by an open port.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Callable

PORT = 1883
# Names the usual all-in-one setups answer to (checked besides this machine and the local network).
HOSTNAMES = ("homeassistant.local", "raspberrypi.local", "zigbee2mqtt.local", "mosquitto.local")

_CONNECT = b"\x10\x16\x00\x04MQTT\x04\x02\x00\x3c\x00\x0anoodle-chk"  # MQTT 3.1.1, clean session, 10 character id


async def probe(host: str, port: int = PORT, timeout: float = 1.0) -> str | None:
    """"ok" if an MQTT broker accepts us, "password" if it wants a login, None if nothing there speaks MQTT."""
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, asyncio.TimeoutError):
        return None
    try:
        writer.write(_CONNECT)
        await writer.drain()
        reply = await asyncio.wait_for(reader.readexactly(4), timeout + 1)
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError):
        return None
    finally:
        writer.close()
    if reply[0] != 0x20 or reply[1] != 2:
        return None
    return "ok" if reply[3] == 0 else "password"


def why_not(state: str | None, host: str, port: int) -> str:
    """The reason a probe failed, in plain words."""
    if state == "password":
        return f"The broker at {host}:{port} needs a username and password, which Noodle cannot use yet. In Mosquitto, allow anonymous access on your home network."
    return f"Nothing answered as an MQTT broker at {host}:{port}. Check the address, and that the broker (for example Mosquitto) is running."


def own_addresses() -> set[str]:
    addresses: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # picks the outgoing interface; sends nothing
            addresses.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        addresses.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return addresses


def local_networks() -> list[ipaddress.IPv4Network]:
    """The /24 around each of this machine's private addresses, where the broker most likely is."""
    nets = []
    for text in sorted(own_addresses()):
        ip = ipaddress.ip_address(text)
        if ip.is_private and not ip.is_loopback and not ip.is_link_local:
            net = ipaddress.ip_network(f"{ip}/24", strict=False)
            if net not in nets:
                nets.append(net)
    return nets


async def _resolve(name: str) -> str | None:
    try:
        info = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(name, PORT, family=socket.AF_INET), 2)
    except (OSError, asyncio.TimeoutError):
        return None
    return info[0][4][0] if info else None


async def find(seconds: float, found: Callable[..., None]) -> None:
    """Look for brokers on this machine, under a few well-known names and on the local network, then stop."""
    seen: set[str] = set(own_addresses())  # this machine is checked once, as 127.0.0.1

    async def check(host: str, label: str | None = None) -> None:
        if host in seen:
            return
        state = await probe(host, PORT, timeout=0.8)
        if state is None:
            return
        seen.add(host)
        found(f"{host}:{PORT}", host=host, port=PORT,
              name=label or f"MQTT broker at {host}",
              detail=f"{host}:{PORT}" + ("" if state == "ok" else " · needs a password, not supported yet"))

    await check("127.0.0.1", "MQTT broker on this computer")
    gate = asyncio.Semaphore(128)

    async def limited(host: str) -> None:
        async with gate:
            await check(host)

    async def named(name: str) -> None:
        if ip := await _resolve(name):
            await limited(ip)

    jobs = [named(n) for n in HOSTNAMES]
    for net in local_networks():
        jobs += [limited(str(h)) for h in net.hosts()]
    await asyncio.wait_for(asyncio.gather(*jobs, return_exceptions=True), max(1.0, seconds))
