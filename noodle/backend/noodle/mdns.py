"""Listen for mDNS announcements for a while. Used by the searches of the integrations whose devices announce
themselves; it runs only while the user has pressed Search, never in the background."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


async def browse(service_types: list[str], seconds: float, on_service: Callable[[str, str, object], Awaitable[None]]) -> None:
    """For `seconds`, call `await on_service(service_type, name, info)` for every service of these types that
    announces itself. `info` is a zeroconf AsyncServiceInfo that has been resolved (addresses, port, properties)."""
    from zeroconf import ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

    zc = AsyncZeroconf()
    pending: set[asyncio.Task] = set()

    async def resolve(service_type: str, name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        if await info.async_request(zc.zeroconf, 3000):
            await on_service(service_type, name, info)

    def changed(zeroconf, service_type, name, state_change) -> None:
        if state_change is ServiceStateChange.Added:
            task = asyncio.ensure_future(resolve(service_type, name))
            pending.add(task)
            task.add_done_callback(pending.discard)

    browser = AsyncServiceBrowser(zc.zeroconf, service_types, handlers=[changed])
    try:
        await asyncio.sleep(seconds)
    finally:
        await browser.async_cancel()
        for task in pending:
            task.cancel()
        await zc.async_close()


def ipv4(info) -> list[str]:
    """The IPv4 addresses of a resolved service."""
    return [a for a in info.parsed_addresses() if ":" not in a]
