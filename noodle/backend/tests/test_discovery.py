import asyncio

from noodle.discovery import Discovery
from noodle.hub import Hub
from noodle.store import Store


def make(tmp_path):
    hub = Hub(Store(tmp_path / "db.sqlite"))
    pushed = []
    hub.broadcast = pushed.append
    return Discovery(hub), pushed


def test_a_search_reports_and_ends(tmp_path):
    async def go():
        discovery, pushed = make(tmp_path)

        async def search(seconds, found):
            found("a", name="One", detail="10.0.0.1")
            await asyncio.sleep(0.01)
            found("a", name="One renamed")
            found("b", name="Two")

        state = discovery.start("x", search, seconds=1)
        assert state["searching"] and state["ends"] > 0
        await asyncio.sleep(0.1)
        done = discovery.state("x")
        assert done["searching"] is False and done["ends"] is None
        assert [f["name"] for f in done["found"]] == ["One renamed", "Two"]
        assert done["found"][0]["detail"] == "10.0.0.1" and not done["found"][0]["added"]
        assert pushed[-1]["type"] == "discovery" and pushed[-1]["searching"] is False
        discovery.mark_added("x", "a")
        assert discovery.state("x")["found"][0]["added"] is True

    asyncio.run(go())


def test_stop_and_errors(tmp_path):
    async def go():
        discovery, _ = make(tmp_path)

        async def forever(seconds, found):
            await asyncio.sleep(60)

        async def broken(seconds, found):
            raise RuntimeError("no network")

        discovery.start("x", forever, seconds=60)
        assert discovery.stop("x")["searching"] is False
        discovery.start("y", broken, seconds=1)
        await asyncio.sleep(0.05)
        assert discovery.state("y")["error"] == "no network" and not discovery.state("y")["searching"]
        assert discovery.state("never")["found"] == []

    asyncio.run(go())


def test_a_new_search_starts_with_an_empty_list(tmp_path):
    async def go():
        discovery, _ = make(tmp_path)

        async def once(seconds, found):
            found("a", name="A")

        discovery.start("x", once, seconds=1)
        await asyncio.sleep(0.05)
        assert len(discovery.state("x")["found"]) == 1
        discovery.start("x", lambda s, f: asyncio.sleep(0.01), seconds=1)
        assert discovery.state("x")["found"] == []

    asyncio.run(go())
