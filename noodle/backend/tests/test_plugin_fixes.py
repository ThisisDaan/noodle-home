"""Fixes from the plugin review: each one has a test that fails without it."""

import asyncio
import os
import tempfile

import pytest

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())

from noodle import config, integrations, main, mdns, plugins  # noqa: E402
from noodle.hub import Device, Hub  # noqa: E402
from noodle.plugins.base import PressButton  # noqa: E402
from noodle.plugins.ble import adapter as ble  # noqa: E402
from noodle.plugins.govee import adapter as govee  # noqa: E402
from noodle.plugins.hue import adapter as hue  # noqa: E402
from noodle.plugins.lan.adapter import LanAdapter  # noqa: E402
from noodle.store import Store  # noqa: E402


def make_hub(tmp_path):
    return Hub(Store(tmp_path / "db.sqlite"))


def test_removing_an_integration_removes_its_devices_by_default(tmp_path):
    hub = make_hub(tmp_path)
    for dev_id, source in (("zigbee:a", "zigbee"), ("matter:1", "matter"), ("hue:x", "hue")):
        hub.upsert(Device(id=dev_id, source=source, name=dev_id))
    by_id = {p.id: p for p in plugins.discover()}
    by_id["zigbee"].on_remove(hub, None)
    by_id["matter"].on_remove(hub, None)
    assert set(hub.devices) == {"hue:x"}  # only the devices of the removed integrations go


class _Found(LanAdapter):
    source = "fake"

    async def add_host(self, host):
        raise PressButton("press it")


def test_a_device_that_needs_a_button_stays_in_the_found_list(tmp_path):
    adapter = _Found(make_hub(tmp_path))
    adapter.nearby["k"] = ("10.0.0.5", "Thing")
    with pytest.raises(PressButton):
        asyncio.run(adapter.add_found("k"))
    assert "k" in adapter.nearby  # the next try, after the button, still finds it


def test_a_failing_plugin_does_not_break_the_integrations_page(monkeypatch):
    plugin = next(p for p in plugins.discover() if p.id == "wled")
    monkeypatch.setattr(type(plugin), "details", lambda self, adapter: 1 / 0)
    described = integrations.describe(plugin.describe(None), plugin, None)
    assert described["id"] == "wled" and "ZeroDivisionError" in described["error"]


def test_a_failing_system_info_does_not_hide_the_others(monkeypatch):
    zigbee = next(p for p in main.PLUGINS if p.id == "zigbee")
    ok = next(p for p in main.PLUGINS if p.id == "matter")

    async def boom(self, adapter):
        raise RuntimeError("down")

    async def fine(self, adapter):
        return {"fine": True}

    monkeypatch.setattr(type(zigbee), "system_info", boom)
    monkeypatch.setattr(type(ok), "system_info", fine)
    result = asyncio.run(main.system())
    assert "zigbee" not in result and result["matter"] == {"fine": True}


def test_saving_settings_does_not_start_an_integration_that_is_not_added(monkeypatch):
    started = []

    async def fake_restart(source):
        started.append(source)

    async def no_wait(seconds):
        return None

    monkeypatch.setattr(main, "restart_adapter", fake_restart)
    monkeypatch.setattr(main.asyncio, "sleep", no_wait)
    monkeypatch.setattr(config, "save", lambda values: None)
    monkeypatch.setattr(integrations, "added_ids", lambda: [])
    asyncio.run(main.save_integration("pihole", main.SettingsBody(values={"pihole_url": "http://x"})))
    assert started == []  # not added: nothing runs
    monkeypatch.setattr(integrations, "added_ids", lambda: ["pihole"])
    asyncio.run(main.save_integration("pihole", main.SettingsBody(values={"pihole_url": "http://x"})))
    assert started == ["pihole"]


def test_govee_asks_for_its_model_after_a_restart(monkeypatch, tmp_path):
    async def fake_exchange(host, port, payload, expect, timeout=3.0):
        return {"onOff": 1, "brightness": 50} if expect == "devStatus" else {"sku": "H6008"}

    monkeypatch.setattr(govee, "exchange", fake_exchange)
    adapter = govee.GoveeAdapter(make_hub(tmp_path))
    device = asyncio.run(adapter.read("abcd", "10.0.0.9"))
    assert device.model == "H6008" and "H6008" in device.name


def test_bluetooth_remembers_what_is_nearby_only_during_a_search(tmp_path):
    adapter = ble.BleAdapter(make_hub(tmp_path))

    class Ad:
        local_name, rssi, manufacturer_data, service_data, service_uuids = "x", -50, {}, {}, []

    class Dev:
        address, name = "AA:BB:CC:DD:EE:FF", "x"

    adapter._seen(Dev(), Ad())
    assert adapter.nearby == {}  # not searching: nothing is kept
    adapter.searching = True
    adapter._seen(Dev(), Ad())
    assert "AA:BB:CC:DD:EE:FF" in adapter.nearby


def test_hue_search_uses_the_bridges_own_announcement(monkeypatch):
    class Info:
        def parsed_addresses(self):
            return ["fe80::1", "192.168.1.57"]

    async def fake_browse(types, seconds, on_service):
        assert types == [hue.MDNS]
        await on_service(hue.MDNS, "Hue._hue._tcp.local.", Info())

    monkeypatch.setattr(mdns, "browse", fake_browse)
    found = []
    asyncio.run(hue.discover(1, found.append))
    assert found == ["192.168.1.57"]  # IPv4 only, and no call to Philips' servers
