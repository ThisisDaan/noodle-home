"""Container status, restart and logs via the Docker Engine API on its unix socket."""

from __future__ import annotations

import os

import httpx

from .. import config


def available() -> bool:
    return os.path.exists(config.DOCKER_SOCKET)


def _client() -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(uds=config.DOCKER_SOCKET)
    return httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=30)


# Web interfaces of containers that run on the host network (Docker cannot list their ports). A container can
# also say where its interface is with a label in compose.yaml: `noodle.webui: "8123"` or `"https:8443"`.
# The names below are only a fallback for containers started before they had that label (compose.yaml has them now).
WEB_UIS = {"homeassistant": "8123", "zigbee2mqtt": "8081", "noodle": "8090", "otbr": "7586"}


def _web_ui(name: str, labels: dict) -> dict | None:
    spec = labels.get("noodle.webui") or labels.get("homepi.webui") or WEB_UIS.get(name)
    if not spec:
        return None
    scheme, _, port = spec.rpartition(":")
    return {"scheme": scheme or "http", "port": int(port)}


def _ports(c: dict) -> list[str]:
    """Published ports as "host→container" (just the number when both are the same), without IPv6 duplicates."""
    seen: dict[tuple, str] = {}
    for p in c.get("Ports", []):
        if "PublicPort" not in p:
            continue
        key = (p["PublicPort"], p["PrivatePort"], p["Type"])
        label = str(p["PublicPort"]) if p["PublicPort"] == p["PrivatePort"] else f"{p['PublicPort']}→{p['PrivatePort']}"
        seen[key] = label + ("/udp" if p["Type"] == "udp" else "")
    return [seen[k] for k in sorted(seen)]


async def containers() -> list[dict]:
    if not available():
        return []
    async with _client() as client:
        items = (await client.get("/containers/json", params={"all": "true"})).json()
    result = []
    for c in items:
        name = c["Names"][0].lstrip("/")
        result.append({
            "id": c["Id"][:12],
            "name": name,
            "image": c["Image"],
            "state": c["State"],
            "status": c["Status"],
            "ports": _ports(c),
            "host_network": c.get("HostConfig", {}).get("NetworkMode") == "host",
            "web": _web_ui(name, c.get("Labels") or {}),
        })
    return sorted(result, key=lambda c: c["name"])


async def restart(name: str) -> None:
    async with _client() as client:
        response = await client.post(f"/containers/{name}/restart", timeout=120)
        response.raise_for_status()


async def logs(name: str, tail: int = 200) -> str:
    async with _client() as client:
        info = (await client.get(f"/containers/{name}/json")).json()
        raw = (await client.get(f"/containers/{name}/logs",
                                params={"stdout": "true", "stderr": "true", "tail": str(tail)})).content
    if info.get("Config", {}).get("Tty"):
        return raw.decode(errors="replace")
    # Without a TTY the stream is multiplexed: 8-byte header (stream, 0, 0, 0, size) per frame.
    out, i = [], 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        out.append(raw[i + 8:i + 8 + size].decode(errors="replace"))
        i += 8 + size
    return "".join(out)
