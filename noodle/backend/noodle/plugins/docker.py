"""Docker containers on this machine: shown on the System page, with restart and logs. Only there when this hub
can reach a Docker socket; without one the hub works the same and the System page has no Docker section."""

from fastapi import APIRouter, Depends, HTTPException

from ..adapters import docker as engine
from .base import Plugin


class DockerPlugin(Plugin):
    id = "docker"
    name = "Docker"
    visible = False  # nothing to add: it is there when the socket is
    order = 250

    async def system_info(self, adapter):
        if not engine.available():
            return {"available": False, "containers": []}
        try:
            return {"available": True, "containers": await engine.containers()}
        except Exception as err:  # the socket exists but Docker does not answer
            return {"available": False, "containers": [], "error": str(err) or type(err).__name__}

    def routes(self, adapter, ctx):
        router = APIRouter(dependencies=[Depends(ctx.require_login)])

        async def known(name: str) -> str:
            if not engine.available():
                raise HTTPException(404, "Docker is not available on this hub")
            if name not in {c["name"] for c in await engine.containers()}:
                raise HTTPException(404, "Unknown container")
            return name

        @router.post("/api/containers/{name}/restart")
        async def restart_container(name: str) -> dict:
            await engine.restart(await known(name))
            return {"ok": True}

        @router.get("/api/containers/{name}/logs")
        async def container_logs(name: str, tail: int = 200) -> dict:
            return {"logs": await engine.logs(await known(name), min(max(tail, 10), 2000))}

        return router


PLUGIN = DockerPlugin()
