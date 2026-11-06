"""UDP discovery for the device adapters: send one probe, then collect the replies for a few seconds.

Only used while the user has pressed Search (see discovery.py); nothing here runs in the background.
"""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

BROADCAST = "255.255.255.255"
RESEND_EVERY = 3.0  # seconds between probes while waiting for answers


async def udp_probe(payload: bytes, port: int, seconds: float, parse: Callable[[bytes, tuple], Any], *,
                    host: str = BROADCAST, multicast: bool = False, bind: int | None = None) -> AsyncIterator[Any]:
    """Send payload to host:port (again every few seconds) for `seconds`, and yield parse(data, addr) for each reply.

    parse returns None, or raises ValueError / KeyError / TypeError, to skip a reply. host defaults to the local
    broadcast address; multicast=True sends to a multicast group instead. bind= answers from that local port.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if multicast:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if bind is not None:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    deadline, last_send = time.time() + seconds, 0.0
    try:
        if bind is not None:
            sock.bind(("", bind))
        while time.time() < deadline:
            if time.time() - last_send > RESEND_EVERY:
                sock.sendto(payload, (host, port))
                last_send = time.time()
            try:
                data, addr = await asyncio.wait_for(loop.sock_recvfrom(sock, 4096), 1.0)
                result = parse(data, addr)
            except (asyncio.TimeoutError, OSError, ValueError, KeyError, TypeError):
                continue
            if result is not None:
                yield result
    finally:
        sock.close()
