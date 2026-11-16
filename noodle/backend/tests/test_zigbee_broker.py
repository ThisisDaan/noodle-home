import asyncio

from noodle.plugins.zigbee import broker


async def _fake_broker(code: int):
    async def handle(reader, writer):
        await reader.read(64)
        writer.write(bytes([0x20, 2, 0, code]))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def test_probe_recognises_a_broker_a_password_and_nothing():
    async def go():
        ok, ok_port = await _fake_broker(0)
        locked, locked_port = await _fake_broker(5)
        async with ok, locked:
            assert await broker.probe("127.0.0.1", ok_port) == "ok"
            assert await broker.probe("127.0.0.1", locked_port) == "password"
        assert await broker.probe("127.0.0.1", ok_port, timeout=0.3) is None  # closed again

    asyncio.run(go())


def test_probe_ignores_something_that_is_not_mqtt():
    async def go():
        async def handle(reader, writer):
            writer.write(b"HTTP/1.1 400\r\n")
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        async with server:
            assert await broker.probe("127.0.0.1", server.sockets[0].getsockname()[1]) is None

    asyncio.run(go())


def test_find_reports_this_computer_and_explains_failures(monkeypatch):
    async def go():
        server, port = await _fake_broker(0)
        monkeypatch.setattr(broker, "PORT", port)
        monkeypatch.setattr(broker, "HOSTNAMES", ())
        monkeypatch.setattr(broker, "local_networks", lambda: [])
        hits = []
        async with server:
            await broker.find(5, lambda key, **info: hits.append((key, info)))
        assert [k for k, _ in hits] == [f"127.0.0.1:{port}"]
        assert hits[0][1]["host"] == "127.0.0.1"

    asyncio.run(go())
    assert "needs a username" in broker.why_not("password", "h", 1883)
    assert "Nothing answered" in broker.why_not(None, "h", 1883)
