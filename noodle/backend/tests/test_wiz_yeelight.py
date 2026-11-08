"""WiZ and Yeelight: the parts that do not need a device (what a reply means, what a command sends)."""

import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())

from noodle.plugins.wiz import adapter as wiz  # noqa: E402
from noodle.plugins.yeelight import adapter as yeelight  # noqa: E402


def test_wiz_module_kinds():
    assert wiz.kind_of("ESP01_SHRGB_03") == "color"
    assert wiz.kind_of("ESP10_SOCKET_06") == "plug"
    assert wiz.kind_of("ESP01_SHTW_01") == "white"


def test_wiz_entities():
    light = wiz.entities_from({"state": True, "dimming": 40, "temp": 3000}, "ESP01_SHTW_01")["light"]
    assert light.state is True and light.brightness == 40 and light.attrs["can"] == ["color_temp"]
    color = wiz.entities_from({"state": False, "dimming": 100, "r": 0, "g": 255, "b": 0}, "ESP01_SHRGB_03")["light"]
    assert "color" in color.attrs["can"] and color.attrs["color"]["h"] == 120.0
    assert "switch" in wiz.entities_from({"state": True}, "ESP10_SOCKET_06")


def test_wiz_commands():
    assert wiz.pilot_for(False, None, None, None) == {"state": False}
    assert wiz.pilot_for(None, 3, None, None) == {"dimming": 10, "state": True}  # never below 10 %, and it turns on
    assert wiz.pilot_for(None, None, 9000, None) == {"temp": 6500, "state": True}
    assert wiz.pilot_for(None, None, None, {"h": 0, "s": 100}) == {"r": 255, "g": 0, "b": 0, "state": True}
    assert wiz.pilot_for(None, None, None, None) == {}


def test_yeelight_ssdp_answer():
    text = ("HTTP/1.1 200 OK\r\nCache-Control: max-age=3584\r\nLocation: yeelight://192.168.1.50:55443\r\n"
            "id: 0x000000000015243f\r\nmodel: color\r\nname: Desk\r\npower: on\r\n\r\n")
    headers = yeelight.parse_ssdp(text)
    assert headers["id"] == "0x000000000015243f" and headers["name"] == "Desk"
    assert yeelight.host_of(headers) == "192.168.1.50" and yeelight.host_of({}) is None


def test_yeelight_entities():
    props = dict(zip(yeelight.PROPS, ["on", "60", "4000", "120", "80", "1", "Desk"]))
    light = yeelight.entities_from(props)["light"]
    assert light.state is True and light.brightness == 60 and light.attrs["color"] == {"h": 120.0, "s": 80.0}
    white = yeelight.entities_from({"power": "off", "bright": "10", "ct": "2700", "hue": ""})["light"]
    assert white.state is False and white.attrs["can"] == ["color_temp"]


def test_yeelight_commands():
    assert yeelight.commands_for(False, None, None, None) == [("set_power", ["off", "smooth", 300])]
    calls = yeelight.commands_for(None, 50, None, {"h": 200, "s": 30})
    assert [c[0] for c in calls] == ["set_power", "set_bright", "set_hsv"]
    assert calls[2][1][:2] == [200, 30]
    assert yeelight.commands_for(None, None, None, None) == []


# --- Govee, Roku, Yamaha MusicCast, Pi-hole

from noodle.plugins.govee import adapter as govee  # noqa: E402
from noodle.plugins.pihole import adapter as pihole  # noqa: E402
from noodle.plugins.roku import adapter as roku  # noqa: E402
from noodle.plugins.yamaha import adapter as yamaha  # noqa: E402


def test_govee_messages():
    cmd, data = govee.parse(b'{"msg":{"cmd":"scan","data":{"ip":"192.168.1.9","device":"1F:80:C5:32:32:36:72:4E","sku":"H6008"}}}')
    assert cmd == "scan" and data["sku"] == "H6008" and govee.device_key(data["device"]) == "1f80c53232367 24e".replace(" ", "")
    try:
        govee.parse(b"nonsense")
        raise AssertionError("should not parse")
    except ValueError:
        pass


def test_govee_entities_and_commands():
    light = govee.entities_from({"onOff": 1, "brightness": 70, "color": {"r": 255, "g": 0, "b": 0}, "colorTemInKelvin": 0})["light"]
    assert light.state is True and light.brightness == 70 and light.attrs["color"]["h"] == 0.0
    assert govee.commands_for(False, None, None, None) == [govee.message("turn", value=0)]
    calls = govee.commands_for(None, 0, 1000, None)
    assert [c["msg"]["cmd"] for c in calls] == ["turn", "brightness", "colorwc"]
    assert calls[1]["msg"]["data"]["value"] == 1 and calls[2]["msg"]["data"]["colorTemInKelvin"] == 2000
    assert govee.commands_for(None, None, None, None) == []


def test_roku_parsing_and_power():
    info = "<device-info><serial-number>X00100</serial-number><user-device-name>Lounge</user-device-name><power-mode>Ready</power-mode><is-tv>false</is-tv></device-info>"
    assert roku.tag(info, "user-device-name") == "Lounge"
    entities = roku.entities_from(info, "Netflix", "play")
    assert entities["power"].state is False and entities["playing"].state is True and entities["app"].state == "Netflix"
    assert roku.entities_from(info.replace("Ready", "PowerOn"), None, None)["power"].state is True
    assert roku.location_host("HTTP/1.1 200 OK\r\nLOCATION: http://192.168.1.40:8060/\r\nST: roku:ecp\r\n") == "192.168.1.40"
    assert roku.keys_for(True, False, True) == ["PowerOn"] and roku.keys_for(False, True, False) == ["Power"]
    assert roku.keys_for(False, True, True) == []


def test_yamaha_entities_and_errors():
    entities = yamaha.entities_from({"power": "on", "volume": 40, "max_volume": 161, "mute": False})
    assert entities["power"].state is True and entities["volume"].attrs["max"] == 161 and entities["mute"].state is False
    assert yamaha.entities_from({"power": "standby"})["power"].state is False
    assert yamaha.check({"response_code": 0, "x": 1})["x"] == 1
    try:
        yamaha.check({"response_code": 3})
        raise AssertionError("should refuse")
    except ValueError:
        pass


def test_pihole_entities():
    entities = pihole.entities_from({"queries": {"total": 1200, "blocked": 300, "percent_blocked": 25.04},
                                     "gravity": {"domains_being_blocked": 90000}}, {"blocking": "disabled"})
    assert entities["blocking"].state is False and entities["queries"].state == 1200
    assert entities["percent"].state == 25.0 and entities["domains"].state == 90000


from noodle.plugins.unifi import adapter as unifi  # noqa: E402


def test_unifi_presence_has_a_grace_period():
    tracked = {"aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"}
    present = unifi.present_macs([{"mac": "AA:BB:CC:DD:EE:01"}, {"mac": "11:22:33:44:55:66"}, {}])
    assert present == {"aa:bb:cc:dd:ee:01", "11:22:33:44:55:66"} and unifi.normalise("AA-BB") == "aa:bb"
    seen: dict = {}
    assert unifi.update_seen(seen, present, tracked, 1000.0) == {"aa:bb:cc:dd:ee:01": True, "aa:bb:cc:dd:ee:02": False}
    later = unifi.update_seen(seen, set(), tracked, 1000.0 + unifi.AWAY_AFTER - 1)  # gone, but not for long
    assert later["aa:bb:cc:dd:ee:01"] is True
    assert unifi.update_seen(seen, set(), tracked, 1000.0 + unifi.AWAY_AFTER + 1)["aa:bb:cc:dd:ee:01"] is False


def test_home_assistant_found_address():
    from noodle.plugins.homeassistant.adapter import found_url
    assert found_url({b"base_url": b"http://homeassistant.local:8123/"}, ["192.168.1.5"], 8123) == "http://homeassistant.local:8123"
    assert found_url({}, ["fe80::1", "192.168.1.5"], 8123) == "http://192.168.1.5:8123"
    assert found_url({}, ["fe80::1"], 8123) is None
