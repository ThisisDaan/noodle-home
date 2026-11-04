"""Looking for new devices happens only when the user asks for it: a search runs for a short time, reports what
it finds, and stops. Nothing scans in the background.

An integration that can search sets `searchable = True` on its plugin and implements
`search(adapter, seconds, found)` and `add_found(adapter, key)` (plugins/base.py). While a search runs, the
state is pushed to the open pages over /api/ws as {"type": "discovery", "id", "searching", "ends", "found", "error"},
so the interface shows the progress without asking for it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from .hub import Hub

log = logging.getLogger(__name__)

SEARCH_SECONDS = 30

Search = Callable[[float, Callable[..., None]], Awaitable[None]]


class Discovery:
    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self._tasks: dict[str, asyncio.Task] = {}
        self._ends: dict[str, float] = {}
        self._total: dict[str, float] = {}
        self._found: dict[str, dict[str, dict]] = {}
        self._error: dict[str, str | None] = {}

    def state(self, search_id: str) -> dict:
        task = self._tasks.get(search_id)
        searching = bool(task and not task.done())
        left = max(0.0, self._ends.get(search_id, 0) - time.time()) if searching else 0.0
        # `remaining` and `total` let a page count down without trusting its clock to match this one.
        return {"searching": searching, "remaining": round(left, 1), "total": self._total.get(search_id, 0),
                "ends": self._ends.get(search_id) if searching else None,
                "found": list(self._found.get(search_id, {}).values()), "error": self._error.get(search_id)}

    def _push(self, search_id: str) -> None:
        self.hub.broadcast({"type": "discovery", "id": search_id, **self.state(search_id)})

    def start(self, search_id: str, search: Search, seconds: float = SEARCH_SECONDS) -> dict:
        """Begin a search (replacing one that is running). `search(seconds, found)` looks for that long and calls
        found(key, name=..., detail=...) for each thing it finds; calling it again with the same key updates it."""
        self.stop(search_id, push=False)
        self._found[search_id], self._error[search_id] = {}, None
        self._ends[search_id], self._total[search_id] = time.time() + seconds, seconds
        self._tasks[search_id] = asyncio.create_task(self._run(search_id, search, seconds))
        self._push(search_id)
        return self.state(search_id)

    async def _run(self, search_id: str, search: Search, seconds: float) -> None:
        def found(key: str, **info) -> None:
            self._found[search_id].setdefault(key, {"key": key, "added": False}).update(info)
            self._push(search_id)

        try:
            await asyncio.wait_for(search(seconds, found), seconds + 5)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            raise
        except Exception as err:
            log.warning("search %s failed: %s", search_id, err)
            self._error[search_id] = str(err) or err.__class__.__name__
        finally:
            if self._tasks.get(search_id) is asyncio.current_task():
                self._tasks.pop(search_id, None)
                self._push(search_id)

    def stop(self, search_id: str, push: bool = True) -> dict:
        if task := self._tasks.pop(search_id, None):
            task.cancel()
        if push:
            self._push(search_id)
        return self.state(search_id)

    def mark_added(self, search_id: str, key: str) -> None:
        if key in self._found.get(search_id, {}):
            self._found[search_id][key]["added"] = True
            self._push(search_id)
