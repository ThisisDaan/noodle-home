"""The Docker Engine API on its unix socket. Only the in-app updater uses it (updates.py): Noodle pulls its new image
and restarts itself. Noodle does not manage other containers."""

from __future__ import annotations

import os

import httpx

from . import config


def available() -> bool:
    return os.path.exists(config.DOCKER_SOCKET)


def _client() -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(uds=config.DOCKER_SOCKET)
    return httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=30)
