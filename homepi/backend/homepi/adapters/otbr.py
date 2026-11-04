"""Thread border router status via the OTBR REST API."""

from __future__ import annotations

import httpx

from .. import config


async def active_dataset_hex() -> str:
    """The active Thread dataset as TLV hex, for handing to matter-server. Never sent to the browser."""
    async with httpx.AsyncClient(base_url=config.OTBR_URL, timeout=5) as client:
        response = await client.get("/node/dataset/active", headers={"Accept": "text/plain"})
        response.raise_for_status()
        return response.text.strip()


async def status() -> dict:
    async with httpx.AsyncClient(base_url=config.OTBR_URL, timeout=5) as client:
        try:
            node = (await client.get("/node", headers={"Accept": "application/json"})).json()
        except (httpx.HTTPError, ValueError) as err:
            return {"reachable": False, "error": str(err)}
        try:
            dataset = (await client.get("/node/dataset/active", headers={"Accept": "application/json"})).json()
        except (httpx.HTTPError, ValueError):
            dataset = {}
    # Only public fields: the active dataset also holds the network key.
    return {
        "reachable": True,
        "state": node.get("state"),
        "network_name": node.get("networkName") or dataset.get("networkName"),
        "channel": dataset.get("channel"),
        "pan_id": dataset.get("panId"),
        "routers": node.get("routerCount"),
        "ext_pan_id": node.get("extPanId"),
    }
