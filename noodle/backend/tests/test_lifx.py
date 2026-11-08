import asyncio
import struct

import pytest

from noodle.plugins.lifx import adapter as lifx
from noodle.plugins.lifx.adapter import FULL, LifxAdapter
from noodle.hub import Hub
from noodle.store import Store

MAC = "d073d5001122"


def state_packet(hue=0, sat=0, bri=FULL, kelvin=3500, power=FULL, label="Desk"):
    payload = struct.pack("<HHHHhH", hue, sat, bri, kelvin, 0, power) + label.encode().ljust(32, b"\0") + b"\0" * 8
    return lifx.build(lifx.LIGHT_STATE, payload, source=1, target=bytes.fromhex(MAC) + b"\0\0")


def service_packet(port=56700):
    return lifx.build(lifx.STATE_SERVICE, struct.pack("<BI", 1, port), source=1, target=bytes.fromhex(MAC) + b"\0\0")


def test_packet_layout():
    packet = lifx.build(lifx.GET_SERVICE, source=0xAABBCCDD, tagged=True, res_required=True)
    assert len(packet) == 36
    assert packet[:2] == (36).to_bytes(2, "little")
    assert int.from_bytes(packet[2:4], "little") == 0x3400  # protocol 1024, addressable, tagged
    assert packet[4:8] == bytes.fromhex("ddccbbaa")
    assert packet[22] == 1 and packet[32:34] == (2).to_bytes(2, "little")
    untagged = lifx.build(lifx.GET_COLOR, source=1, target=bytes.fromhex(MAC) + b"\0\0", seq=7)
    assert int.from_bytes(untagged[2:4], "little") == 0x1400 and untagged[8:14] == bytes.fromhex(MAC)
    assert untagged[23] == 7


def test_parse_round_trip_and_junk():
    msg_type, mac, payload = lifx.parse(state_packet(label="Lamp"))
    assert (msg_type, mac) == (lifx.LIGHT_STATE, MAC)
    assert lifx.read_state(payload)["label"] == "Lamp"
    assert lifx.parse(b"short") is None and lifx.parse(state_packet() + b"x") is None


class Capture:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((lifx.parse(data), addr))


def adapter_with_bulb(tmp_path):
    hub = Hub(Store(tmp_path / "db.sqlite"))
    adapter = LifxAdapter(hub)
    hub.register(adapter)
    adapter._protocol = lifx._Protocol(lambda *a: None)
    adapter._protocol.transport = Capture()
    adapter.running = True
    adapter.bulbs[f"lifx:{MAC}"] = lifx.Bulb(MAC, ("192.168.1.50", 56700))  # one the user added earlier
    adapter._packet(state_packet(), ("192.168.1.50", 56700))
    return hub, adapter


def test_a_bulb_appears_with_its_state(tmp_path):
    hub, _ = adapter_with_bulb(tmp_path)
    device = hub.devices[f"lifx:{MAC}"]
    light = device.entities["light"]
    assert (device.name, device.manufacturer, device.available) == ("Desk", "LIFX", True)
    assert (light.state, light.brightness, light.attrs["color_temp"]) == (True, 100, 3500)
    assert light.attrs["can"] == ["color_temp", "color"]


def test_state_updates_follow_the_bulb(tmp_path):
    hub, adapter = adapter_with_bulb(tmp_path)
    adapter._packet(state_packet(hue=21845, sat=FULL, bri=FULL // 2, power=0), ("192.168.1.50", 56700))
    light = hub.devices[f"lifx:{MAC}"].entities["light"]
    assert light.state is False and light.brightness == 50
    assert light.attrs["color"] == {"h": 120.0, "s": 100.0}


def test_commands_become_packets(tmp_path):
    hub, adapter = adapter_with_bulb(tmp_path)
    adapter._protocol.transport.sent.clear()
    asyncio.run(hub.command(f"lifx:{MAC}", "light", color_temp=2700))
    packets = [(p[0][0], p[0][2]) for p in adapter._protocol.transport.sent]
    set_color = next(payload for kind, payload in packets if kind == lifx.SET_COLOR)
    _, hue, sat, bri, kelvin, ms = struct.unpack("<BHHHHI", set_color)
    assert (hue, sat, kelvin) == (0, 0, 2700) and bri == FULL
    assert all(addr == ("192.168.1.50", 56700) for _, addr in adapter._protocol.transport.sent)


def test_brightness_color_and_power(tmp_path):
    hub, adapter = adapter_with_bulb(tmp_path)
    key = f"lifx:{MAC}"
    adapter._packet(state_packet(power=0), ("192.168.1.50", 56700))
    adapter._protocol.transport.sent.clear()
    asyncio.run(hub.command(key, "light", brightness=40))  # dimming an off bulb also turns it on
    kinds = [p[0][0] for p in adapter._protocol.transport.sent]
    assert lifx.SET_COLOR in kinds and lifx.SET_LIGHT_POWER in kinds
    assert hub.devices[key].entities["light"].state is True and hub.devices[key].entities["light"].brightness == 40
    asyncio.run(hub.command(key, "light", color={"h": 120, "s": 100}))
    assert hub.devices[key].entities["light"].attrs["color"] == {"h": 120.0, "s": 100.0}
    asyncio.run(hub.command(key, "light", toggle=True))
    assert hub.devices[key].entities["light"].state is False


def test_unreachable_and_gone(tmp_path):
    hub, adapter = adapter_with_bulb(tmp_path)
    adapter.bulbs[f"lifx:{MAC}"].heard -= 60
    adapter._check_gone(__import__("time").time())
    assert hub.devices[f"lifx:{MAC}"].available is False
    adapter.running = False
    with pytest.raises(RuntimeError):
        asyncio.run(hub.command(f"lifx:{MAC}", "light", on=True))


def test_nothing_is_noticed_unless_a_search_is_running(tmp_path):
    hub, adapter = adapter_with_bulb(tmp_path)
    other = bytes.fromhex("d073d5aabbcc") + b"\0\0"
    packet = lifx.build(lifx.STATE_SERVICE, struct.pack("<BI", 1, 56700), source=1, target=other)
    adapter._packet(packet, ("192.168.1.60", 56700))
    assert adapter.nearby == {} and len(adapter.bulbs) == 1


def test_a_search_lists_new_bulbs_and_adding_keeps_them(tmp_path, monkeypatch):
    hub, adapter = adapter_with_bulb(tmp_path)
    saved = []
    monkeypatch.setattr(lifx.config, "save", lambda values: saved.append(values))
    seen = {}
    adapter._found = lambda key, **info: seen.setdefault(key, {}).update(info)
    new_mac = "d073d5aabbcc"
    target = bytes.fromhex(new_mac) + b"\0\0"
    adapter._packet(lifx.build(lifx.STATE_SERVICE, struct.pack("<BI", 1, 56700), source=1, target=target),
                    ("192.168.1.60", 56700))
    assert seen[new_mac]["detail"] == "192.168.1.60" and f"lifx:{new_mac}" not in hub.devices
    payload = struct.pack("<HHHHhH", 0, 0, FULL, 3500, 0, FULL) + b"Hall".ljust(32, b"\0") + b"\0" * 8
    adapter._packet(lifx.build(lifx.LIGHT_STATE, payload, source=1, target=target), ("192.168.1.60", 56700))
    assert seen[new_mac]["name"] == "Hall"
    adapter._found = None
    adapter.add_bulb(new_mac)
    assert saved[-1] == {"lifx_bulbs": {new_mac: "192.168.1.60"}} and hub.devices[f"lifx:{new_mac}"].name == "Hall"
    with pytest.raises(KeyError):
        adapter.add_bulb(new_mac)


def test_search_broadcasts_only_while_it_runs(tmp_path, monkeypatch):
    hub, adapter = adapter_with_bulb(tmp_path)
    monkeypatch.setattr(lifx, "SEARCH_PACKET_EVERY", 0.01)
    adapter._protocol.transport.sent.clear()
    asyncio.run(adapter.search(0.05, lambda *a, **k: None))
    sent = len(adapter._protocol.transport.sent)
    assert sent >= 2 and all(p[0][0] == lifx.GET_SERVICE for p in adapter._protocol.transport.sent)
    assert adapter._found is None
    asyncio.run(asyncio.sleep(0.05))
    assert len(adapter._protocol.transport.sent) == sent  # nothing more once the search is over


def test_a_moved_bulb_keeps_working(tmp_path, monkeypatch):
    hub, adapter = adapter_with_bulb(tmp_path)
    saved = []
    monkeypatch.setattr(lifx.config, "save", lambda values: saved.append(values))
    adapter._packet(service_packet(), ("192.168.1.77", 56700))
    assert adapter.bulbs[f"lifx:{MAC}"].addr == ("192.168.1.77", 56700)
    assert saved[-1] == {"lifx_bulbs": {MAC: "192.168.1.77"}}
