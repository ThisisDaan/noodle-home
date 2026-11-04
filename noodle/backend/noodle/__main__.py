"""Run with: noodle   (or: python -m noodle)

  noodle                    start the hub
  noodle validate [PATH..]  check flow files (default: the config/flows folder)
  noodle schema             print the JSON Schema of the flow files
  noodle --version
"""

import asyncio
import sys

from . import __version__


async def _serve_extra(config) -> None:
    """The same app on a second port (80). Its lifespan is off: the first server already started everything."""
    import uvicorn

    server = uvicorn.Server(uvicorn.Config("noodle.main:app", host="0.0.0.0", port=config.EXTRA_PORT, loop="none",
                                           proxy_headers=False, lifespan="off"))
    try:
        await server.serve()
    except SystemExit:
        pass  # the port is taken or not allowed; the main port still works


async def _serve() -> None:
    import uvicorn

    from . import config

    server = uvicorn.Server(uvicorn.Config("noodle.main:app", host="0.0.0.0", port=config.PORT, loop="none",
                                           proxy_headers=False))
    extra = [_serve_extra(config)] if config.EXTRA_PORT and config.EXTRA_PORT != config.PORT else []
    await asyncio.gather(server.serve(), *extra)


def serve() -> None:
    if sys.platform == "win32":  # aiomqtt needs a selector loop; only matters for local development
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_serve())


def cli(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["--version"], ["-V"]):
        print(__version__)
        return 0
    if argv[:1] in (["--help"], ["-h"]):
        print(__doc__.strip())
        return 0
    if argv[:1] in (["validate"], ["schema"]):
        from . import config, flowfiles

        return flowfiles.cli(argv, config.CONFIG_DIR / "flows")
    if argv:
        print(f"Unknown command: {argv[0]}\n\n{__doc__.strip()}", file=sys.stderr)
        return 2
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
