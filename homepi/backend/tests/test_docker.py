import os
import tempfile

os.environ.setdefault("HOMEPI_DATA", tempfile.mkdtemp())
os.environ["HOMEPI_AUTOMATIONS"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from homepi import main  # noqa: E402
from homepi.adapters import docker as engine  # noqa: E402
from homepi.adapters import otbr  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    async def no_thread():
        return {"reachable": False}

    monkeypatch.setattr(otbr, "status", no_thread)
    main.store.db.execute("DELETE FROM settings WHERE key IN ('password', 'setup_started')")
    c = TestClient(main.app)
    assert c.post("/api/auth/setup", json={"password": "correct horse"}).status_code == 200
    yield c
    main.store.db.execute("DELETE FROM settings WHERE key IN ('password', 'setup_started')")


def test_without_a_docker_socket_the_hub_just_has_no_docker_section(client, monkeypatch):
    monkeypatch.setattr(engine, "available", lambda: False)
    system = client.get("/api/system").json()
    assert system["docker"] == {"available": False, "containers": []}
    assert {"zigbee", "matter"} <= system.keys() and "thread" in system["matter"]
    assert "containers" not in system and "docker_available" not in system
    assert client.post("/api/containers/homeassistant/restart").status_code == 404


def test_with_a_socket_containers_are_listed_and_can_be_restarted(client, monkeypatch):
    calls = []

    async def containers():
        return [{"id": "abc", "name": "mosquitto", "state": "running"}]

    async def restart(name):
        calls.append(name)

    async def logs(name, tail):
        return f"log of {name} ({tail})"

    monkeypatch.setattr(engine, "available", lambda: True)
    monkeypatch.setattr(engine, "containers", containers)
    monkeypatch.setattr(engine, "restart", restart)
    monkeypatch.setattr(engine, "logs", logs)
    assert client.get("/api/system").json()["docker"]["containers"][0]["name"] == "mosquitto"
    assert client.post("/api/containers/mosquitto/restart").json() == {"ok": True} and calls == ["mosquitto"]
    assert client.get("/api/containers/mosquitto/logs?tail=5000").json() == {"logs": "log of mosquitto (2000)"}
    assert client.post("/api/containers/other/restart").status_code == 404 and calls == ["mosquitto"]


def test_a_socket_that_does_not_answer_is_not_an_error(client, monkeypatch):
    async def broken():
        raise OSError("connection refused")

    monkeypatch.setattr(engine, "available", lambda: True)
    monkeypatch.setattr(engine, "containers", broken)
    info = client.get("/api/system").json()["docker"]
    assert info["available"] is False and "refused" in info["error"]


def test_container_routes_need_a_login():
    assert TestClient(main.app).get("/api/containers/x/logs").status_code == 401
