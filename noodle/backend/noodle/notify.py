"""Phone notifications through two channels at once:

- local: pushed to the Noodle app over its open connection (works on the home network, no internet needed)
- ntfy (https://ntfy.sh or a self-hosted server): works anywhere, through the ntfy app
"""

from __future__ import annotations

import logging
import uuid
from typing import Callable

import httpx

from . import config

log = logging.getLogger(__name__)

PRIORITIES = {"low": "2", "default": "3", "high": "4", "urgent": "5"}


# Set by main: hands a message to every open Noodle app connection, and says how many there are.
publish: Callable[[dict], None] = lambda message: None
app_clients: Callable[[], int] = lambda: 0


def configured() -> bool:
    """Whether ntfy is set up (the local channel needs no setup)."""
    return bool(config.NTFY_TOPIC)


async def send(message: str, title: str = "Noodle", priority: str = "default", tags: str = "",
               buttons: list[tuple[str, str]] | None = None, service: str = "all") -> dict:
    """buttons: (label, url) pairs; tapping one POSTs to the url (only works where the phone can reach it).
    service: "all", "app" (Noodle app only) or "ntfy" (ntfy only). Returns which channels were used."""
    use_app, use_ntfy = service in ("all", "app"), service in ("all", "ntfy")
    local = app_clients() if use_app else 0
    ntfy = use_ntfy and configured()
    if not ntfy and not local:
        raise RuntimeError({"app": "No phone is connected to the Noodle app, so there is nobody to notify",
                            "ntfy": "ntfy is not set up (no topic), so there is nobody to notify"}.get(
            service, "No phone is connected and no NTFY_TOPIC is set, so there is nobody to notify"))
    if local:
        publish({"type": "notification", "id": uuid.uuid4().hex, "title": title, "message": message,
                 "priority": priority, "tags": tags,
                 "buttons": [{"label": label, "url": url} for label, url in (buttons or [])[:3]]})
        log.info("notification pushed to %d app connection(s): %s", local, title)
    if ntfy:
        await _ntfy(message, title, priority, tags, buttons)
    return {"local": local, "ntfy": ntfy}


async def _ntfy(message: str, title: str, priority: str, tags: str, buttons: list[tuple[str, str]] | None) -> None:
    headers = {"Title": title.encode("utf-8").decode("latin-1", "ignore"), "Priority": PRIORITIES.get(priority, "3")}
    if tags:
        headers["Tags"] = tags
    if buttons:
        headers["Actions"] = "; ".join(
            f"http, {label.replace(',', ' ')}, {url}, method=POST, clear=true" for label, url in buttons[:3])
    # One retry: a lone timeout on the internet link should not fail a whole automation.
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(f"{config.NTFY_URL}/{config.NTFY_TOPIC}", content=message.encode("utf-8"),
                                             headers=headers)
                response.raise_for_status()
            break
        except httpx.TransportError as err:  # timeouts and refused connections have no message of their own
            if attempt == 1:
                log.warning("ntfy not reachable (%s), trying again", err.__class__.__name__)
                continue
            raise RuntimeError(f"Could not reach ntfy at {config.NTFY_URL} ({err.__class__.__name__}). "
                               "Check that this hub has internet access, or set a local ntfy address.") from err
    log.info("notification sent to ntfy: %s", title)
