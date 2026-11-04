"""Spoken announcements on a Google speaker (Chromecast), using Google Translate's TTS audio.

The speaker is found by name over mDNS once; after that homepi connects to its
address directly, because discovery on a busy network does not always answer in time.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import urllib.parse

import pychromecast

log = logging.getLogger(__name__)
_hosts: dict[str, str] = {}
_casts: dict[str, pychromecast.Chromecast] = {}


def _host(name: str) -> str:
    try:
        ipaddress.ip_address(name)
        return name  # an address was given directly
    except ValueError:
        pass
    if name in _hosts:
        return _hosts[name]
    for _ in range(3):
        services, browser = pychromecast.discovery.discover_listed_chromecasts(friendly_names=[name],
                                                                                  discovery_timeout=8)
        browser.stop_discovery()
        if services:
            _hosts[name] = services[0].host
            return _hosts[name]
    raise LookupError(f"speaker '{name}' not found on the network")


def _cast(name: str) -> pychromecast.Chromecast:
    cast = _casts.get(name)
    if cast is None or not cast.socket_client.is_connected:
        cast = pychromecast.get_chromecast_from_host((_host(name), 8009, None, None, None))
        cast.wait(timeout=10)
        _casts[name] = cast
    return cast


def _play(name: str, message: str, language: str) -> None:
    url = "https://translate.google.com/translate_tts?" + urllib.parse.urlencode(
        {"ie": "UTF-8", "client": "tw-ob", "tl": language, "q": message[:200]})
    cast = _cast(name)
    cast.media_controller.play_media(url, "audio/mpeg")
    cast.media_controller.block_until_active(timeout=10)


async def say(speaker: str, message: str, language: str = "nl") -> None:
    try:
        await asyncio.to_thread(_play, speaker, message, language)
    except Exception:
        # The speaker may have a new address or dropped the connection: start fresh next time.
        _hosts.pop(speaker, None)
        cast = _casts.pop(speaker, None)
        if cast:
            cast.disconnect(blocking=False)
        raise
    log.info("said on %s: %s", speaker, message)
