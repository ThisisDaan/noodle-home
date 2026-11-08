"""Update check against GitHub releases, and (in Docker) pulling the new image and restarting into it.

Nothing here runs by itself: the System page asks when the user presses "Check for updates"."""

from __future__ import annotations

import json
import re

import httpx

from . import __version__, config
from . import dockerapi as docker

REPO = config.UPDATE_REPO


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version.split("-")[0])[:3])


def newer(latest: str, current: str) -> bool:
    try:
        return _parse(latest) > _parse(current)
    except ValueError:
        return False


async def check() -> dict:
    result = {"current": __version__, "latest": None, "available": False, "url": None, "notes": "", "error": None}
    try:
        async with httpx.AsyncClient(timeout=15, headers={"Accept": "application/vnd.github+json"}) as client:
            response = await client.get(f"https://api.github.com/repos/{REPO}/releases/latest")
        if response.status_code == 404:
            result["error"] = "No release has been published yet."
        else:
            response.raise_for_status()
            release = response.json()
            tag = release["tag_name"].lstrip("v")
            result.update(latest=tag, available=newer(tag, __version__), url=release.get("html_url"),
                          notes=(release.get("body") or "")[:2000])
    except Exception as err:
        result["error"] = f"Could not reach GitHub: {err}"
    result["can_install"] = await can_install()
    return result


async def _own_image() -> str | None:
    if not docker.available():
        return None
    try:
        async with docker._client() as client:
            info = (await client.get(f"/containers/{config.CONTAINER_NAME}/json")).json()
        image = info["Config"]["Image"]
    except Exception:
        return None
    # A locally built image has no registry to pull from.
    return image if "/" in image and not image.startswith("sha256:") else None


async def can_install() -> bool:
    return await _own_image() is not None


# Runs in a throwaway container from the new image: replaces the hub's container with one made from the same
# settings and the new image. The old one is kept (renamed) until the new one has started.
HELPER = r'''
import json, sys, time, httpx
name, image = sys.argv[1], sys.argv[2]
c = httpx.Client(transport=httpx.HTTPTransport(uds="/var/run/docker.sock"), base_url="http://docker", timeout=120)
time.sleep(3)
old = c.get(f"/containers/{name}/json").json()
body = dict(old["Config"], Image=image, HostConfig=old["HostConfig"])
if old["HostConfig"].get("NetworkMode") not in ("host", "none", "default"):
    body["NetworkingConfig"] = {"EndpointsConfig": {n: {} for n in old["NetworkSettings"]["Networks"]}}
c.post(f"/containers/{name}/stop").raise_for_status()
c.post(f"/containers/{name}/rename", params={"name": name + "-old"}).raise_for_status()
try:
    made = c.post("/containers/create", params={"name": name}, json=body)
    made.raise_for_status()
    c.post(f"/containers/{made.json()['Id']}/start").raise_for_status()
except Exception:
    c.delete(f"/containers/{name}", params={"force": "true"})
    c.post(f"/containers/{name}-old/rename", params={"name": name})
    c.post(f"/containers/{name}/start")
    raise
c.delete(f"/containers/{name}-old")
'''


async def install() -> None:
    image = await _own_image()
    if image is None:
        raise RuntimeError("This hub was not started from a published image, so it cannot update itself.")
    repo, _, tag = image.rpartition(":") if ":" in image.rsplit("/", 1)[-1] else (image, "", "latest")
    async with docker._client() as client:
        client.timeout = 600
        pull = await client.post("/images/create", params={"fromImage": repo, "tag": tag})
        pull.raise_for_status()
        for line in pull.text.splitlines():
            if line.strip() and "error" in json.loads(line):
                raise RuntimeError(json.loads(line)["error"])
        made = await client.post("/containers/create", json={
            "Image": f"{repo}:{tag}",
            "Entrypoint": ["python", "-c", HELPER],
            "Cmd": [config.CONTAINER_NAME, f"{repo}:{tag}"],
            "HostConfig": {"AutoRemove": True, "Binds": [f"{config.DOCKER_SOCKET}:/var/run/docker.sock"]},
        })
        made.raise_for_status()
        (await client.post(f"/containers/{made.json()['Id']}/start")).raise_for_status()
