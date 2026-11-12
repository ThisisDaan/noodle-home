"""Setting up a new Shelly that is not on the Wi-Fi yet: it opens its own network, the hub joins it for a moment,
hands over the home Wi-Fi, goes back and waits for the Shelly to show up (plugins/shelly/hotspot.py)."""

import asyncio
import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())
os.environ["NOODLE_AUTOMATIONS"] = "0"

import httpx  # noqa: E402
import pytest  # noqa: E402

from noodle import config, mdns  # noqa: E402
from noodle.discovery import Discovery  # noqa: E402
from noodle.plugins.shelly import adapter as shelly, hotspot  # noqa: E402

SCAN = "\n".join([
    "Home\\:Net:2437 MHz:80:*",  # a ':' in the name is escaped
    "Home\\:Net:5180 MHz:90:*",
    "Fast5G:5500 MHz:95:",
    "shelly1-A4CF12B3C4D5:2412 MHz:60:",
    "shellyplug-s-7C87CE:2462 MHz:40:",
    ":2412 MHz:20:",  # hidden network
])


class FakeHub:
    def __init__(self):
        self.devices = {}

    def upsert(self, device):
        self.devices[device.id] = device

    def changed(self, device):
        pass

    def remove(self, device_id):
        self.devices.pop(device_id, None)


class FakeNmcli:
    def __init__(self, wired=True, fail=None):
        self.calls, self.wired, self.fail = [], wired, fail

    async def __call__(self, args):
        self.calls.append(args)
        if self.fail:
            raise hotspot.WifiError(self.fail)
        if args[-1] == "device" and "DEVICE,TYPE,STATE" in args:
            return "wlan0:wifi:connected\neth0:ethernet:" + ("connected" if self.wired else "unavailable") + "\nlo:loopback:unmanaged\n"
        if "wifi" in args and "list" in args:
            return SCAN
        if "--active" in args:
            return "1111-home:wlan0\n2222-eth:eth0\n"
        return ""


def test_terse_lines_and_shelly_network_names():
    assert hotspot.split_terse("a\\:b:c\\\\d:") == ["a:b", "c\\d", ""]
    assert hotspot.is_shelly_ap("shelly1-A4CF12") and hotspot.is_shelly_ap("ShellyPlus1PM-A8032AB12345")
    assert hotspot.is_shelly_ap("shellyplug-s-7C87CE")
    assert not hotspot.is_shelly_ap("Shelly's house") and not hotspot.is_shelly_ap("shelly")
    assert hotspot.ap_name("shellyplug-s-7C87CE") == "Shelly plug-s" and hotspot.ap_name("shelly1-A4CF12") == "Shelly 1"
    nets = hotspot.parse_networks(SCAN)
    home = next(n for n in nets if n.ssid == "Home:Net")
    assert home.in_use and home.freq == 2437 and nets[0].ssid == "Home:Net"


def test_explain_turns_nmcli_errors_into_sentences():
    assert hotspot.explain("Error: Not authorized to control networking.") == hotspot.NOT_ALLOWED
    assert "out of range" in hotspot.explain("Error: No network with SSID 'shelly1-x' found.")


def test_search_lists_new_shellies_with_the_24ghz_networks(monkeypatch):
    async def no_mdns(types, seconds, on_service, until=None):
        pass

    monkeypatch.setattr(mdns, "browse", no_mdns)

    async def go():
        adapter = shelly.ShellyAdapter(FakeHub())
        adapter.http = httpx.AsyncClient()
        adapter.wifi = hotspot.NmcliWifi(FakeNmcli(wired=False))
        seen = {}
        await adapter.search(1, lambda key, **info: seen.__setitem__(key, info))
        await adapter.http.aclose()
        return seen

    seen = asyncio.run(go())
    assert set(seen) == {"ap:shelly1-A4CF12B3C4D5", "ap:shellyplug-s-7C87CE"}
    wifi = seen["ap:shelly1-A4CF12B3C4D5"]["wifi"]
    assert wifi == {"networks": ["Home:Net", "Fast5G"], "current": "Home:Net", "offline": True,
                    "only5": ["Fast5G"]}  # no Shellies; 2.4 GHz first


def test_search_without_networkmanager_leaves_a_note(monkeypatch):
    async def no_mdns(types, seconds, on_service, until=None):
        pass

    monkeypatch.setattr(mdns, "browse", no_mdns)

    async def go():
        discovery = Discovery(type("H", (), {"broadcast": lambda self, msg: None})())
        adapter = shelly.ShellyAdapter(FakeHub())
        adapter.http = httpx.AsyncClient()
        adapter.wifi = hotspot.NmcliWifi(FakeNmcli(fail=hotspot.NO_NMCLI))
        discovery.start("shelly", adapter.search, seconds=0.2)
        await asyncio.sleep(0.5)
        await adapter.http.aclose()
        return discovery.state("shelly")

    state = asyncio.run(go())
    assert state["error"] is None and state["found"] == []
    assert len(state["notes"]) == 1 and "192.168.33.1" in state["notes"][0]


def _shelly(gen, requests, auth=False):
    def handler(request):
        requests.append(request)
        host, path = request.url.host, request.url.path
        if path == "/shelly":
            return httpx.Response(200, json={"mac": "A4CF12B3C4D5", "gen": gen, "type": "SHSW-1", "auth": auth})
        if host == hotspot.SETUP_ADDRESS and path in ("/settings/sta", "/rpc"):
            return httpx.Response(200, json={"restart_required": False} if gen >= 2 else {"wifi_sta": {}})
        if path == "/status":
            return httpx.Response(200, json={"relays": [{"ison": False}]})
        return httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_gen1_setup_sends_the_wifi_as_a_form_and_adds_it(monkeypatch):
    saved, requests, steps = {}, [], []
    monkeypatch.setattr(config, "save", lambda values: saved.update(values))

    async def announce(types, seconds, on_service, until=None):
        class Info:
            def parsed_addresses(self):
                return ["192.168.1.77"]
        await on_service(types[0], "shelly1-A4CF12B3C4D5._http._tcp.local.", Info())
        assert until is not None and until.is_set()

    monkeypatch.setattr(mdns, "browse", announce)
    nmcli = FakeNmcli()

    async def go():
        hub = FakeHub()
        adapter = shelly.ShellyAdapter(hub)
        adapter.http, adapter.running = _shelly(1, requests), True
        adapter.wifi = hotspot.NmcliWifi(nmcli)
        adapter.hotspots["ap:shelly1-A4CF12B3C4D5"] = {"ssid": "shelly1-A4CF12B3C4D5", "device": "wlan0"}
        await adapter.add_found("ap:shelly1-A4CF12B3C4D5", wifi_ssid="Home:Net", wifi_password="s3cret pass",
                                report=steps.append)
        return hub, adapter

    hub, adapter = asyncio.run(go())
    form = next(r for r in requests if r.url.path == "/settings/sta")
    assert form.method == "POST" and "s3cret" not in str(form.url)  # the password never goes in a URL
    assert dict(httpx.QueryParams(form.content.decode())) == {"enabled": "1", "ssid": "Home:Net", "key": "s3cret pass"}
    assert saved == {"shelly_devices": {"a4cf12b3c4d5": "192.168.1.77"}} and "shelly:a4cf12b3c4d5" in hub.devices
    assert not adapter.hotspots
    joined = next(c for c in nmcli.calls if "connect" in c)
    assert joined[joined.index("connect") + 1] == "shelly1-A4CF12B3C4D5" and hotspot.CONNECTION in joined
    assert ["--wait", "40", "connection", "up", "uuid", "1111-home"] in nmcli.calls  # back to the home network
    assert steps[0].startswith("Joining") and steps[-1] == "Adding it…"


def test_gen2_setup_uses_wifi_setconfig():
    requests = []

    async def go():
        async with _shelly(2, requests) as http:
            return await hotspot.configure(http, "Home", "pw")

    assert asyncio.run(go()) == "a4cf12b3c4d5"
    rpc = next(r for r in requests if r.url.path == "/rpc")
    import json
    body = json.loads(rpc.content)
    assert body["method"] == "WiFi.SetConfig" and body["params"]["config"]["sta"] == {"ssid": "Home", "pass": "pw", "enable": True}


def test_a_shelly_with_a_password_is_refused():
    async def go():
        async with _shelly(1, [], auth=True) as http:
            await hotspot.configure(http, "Home", "pw")

    with pytest.raises(ValueError, match="password set"):
        asyncio.run(go())


def test_setup_goes_back_home_even_when_it_fails_and_says_when_it_never_shows_up(monkeypatch):
    async def silent(types, seconds, on_service, until=None):
        pass

    monkeypatch.setattr(mdns, "browse", silent)
    nmcli = FakeNmcli()

    async def go():
        adapter = shelly.ShellyAdapter(FakeHub())
        adapter.http = _shelly(1, [])
        adapter.wifi = hotspot.NmcliWifi(nmcli)
        adapter.hotspots["ap:shelly1-A4CF12B3C4D5"] = {"ssid": "shelly1-A4CF12B3C4D5", "device": "wlan0"}
        with pytest.raises(ValueError, match="did not show up on Home"):
            await adapter.add_found("ap:shelly1-A4CF12B3C4D5", wifi_ssid="Home", wifi_password="wrong")
        with pytest.raises(ValueError, match="Pick the Wi-Fi"):
            await adapter.add_found("ap:shelly1-A4CF12B3C4D5")
        with pytest.raises(KeyError):
            await adapter.add_found("ap:gone", wifi_ssid="Home")

    asyncio.run(go())
    assert ["connection", "delete", "id", hotspot.CONNECTION] in nmcli.calls


# --- Windows (netsh wlan)

INTERFACES = """
There is 1 interface on the system:

    Name                   : WiFi
    Description            : Some Wireless Adapter
    GUID                   : 00000000-0000-0000-0000-000000000000
    State                  : connected
    SSID                   : Home Net
    AP BSSID               : 00:11:22:33:44:55
    Band                   : 5 GHz
    Channel                : 100
    Signal                 : 82%
    Profile                : Home Net

"""

NETWORKS = """
Interface name : WiFi
There are 3 networks currently visible.

SSID 1 : Home Net
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    BSSID 1                 : 00:11:22:33:44:55
         Signal             : 82%
         Band               : 5 GHz
         Channel            : 100
    BSSID 2                 : 00:11:22:33:44:56
         Signal             : 60%
         Band               : 2.4 GHz
         Channel            : 6

SSID 2 : shelly1-A4CF12
    Network type            : Infrastructure
    Authentication          : Open
    BSSID 1                 : a4:cf:12:00:00:01
         Signal             : 70%
         Channel            : 1

SSID 3 : Neighbour5
    BSSID 1                 : 00:aa:bb:cc:dd:ee
         Signal             : 30%
         Band               : 5 GHz
         Channel            : 36
"""


class FakeNetsh:
    def __init__(self):
        self.calls, self.on = [], "Home Net"

    async def __call__(self, args):
        self.calls.append(args)
        if args[:3] == ["wlan", "show", "interfaces"]:
            return INTERFACES.replace(": Home Net\n", f": {self.on}\n", 1)
        if args[:3] == ["wlan", "show", "networks"]:
            return NETWORKS
        if args[:2] == ["wlan", "connect"] and any(a.startswith("ssid=") for a in args):
            self.on = next(a for a in args if a.startswith("ssid="))[5:]
        return ""


def test_netsh_output_is_read_by_shape_not_by_language():
    assert hotspot.parse_interfaces(INTERFACES) == [{"name": "WiFi", "ssid": "Home Net", "profile": "Home Net"}]
    dutch = INTERFACES.replace("Name ", "Naam ").replace("Profile ", "Profiel ")
    assert hotspot.parse_interfaces(dutch)[0] == {"name": "WiFi", "ssid": "Home Net", "profile": "Home Net"}
    nets = {n.ssid: n for n in hotspot.parse_netsh_networks(NETWORKS, "Home Net")}
    assert nets["Home Net"].in_use and hotspot.is_24(nets["Home Net"].freq) and nets["Home Net"].signal == 82
    assert hotspot.is_24(nets["shelly1-A4CF12"].freq)  # from the channel when there is no band line
    assert not hotspot.is_24(nets["Neighbour5"].freq)
    assert hotspot.explain("The location permission is not granted. See Privacy settings.") == hotspot.LOCATION


def test_netsh_joins_the_shelly_with_a_temporary_open_profile_and_goes_back():
    netsh = FakeNetsh()

    async def go():
        wifi = hotspot.NetshWifi(netsh)
        device = await wifi.device()
        back = await wifi.active(device)
        await wifi.join(device, "shelly1-A4CF12")
        await wifi.leave(back)
        return device, back

    device, back = asyncio.run(go())
    assert device == "WiFi" and back == "Home Net"
    added = next(c for c in netsh.calls if c[:3] == ["wlan", "add", "profile"])
    assert "user=current" in added and "interface=WiFi" in added
    assert ["wlan", "connect", f"name={hotspot.CONNECTION}", "ssid=shelly1-A4CF12", "interface=WiFi"] in netsh.calls
    assert ["wlan", "delete", "profile", f"name={hotspot.CONNECTION}", "interface=WiFi"] in netsh.calls
    assert netsh.calls[-1] == ["wlan", "connect", "name=Home Net", "interface=WiFi"]


def test_profile_xml_escapes_the_name():
    xml = hotspot._profile_xml("a<b&c")
    assert "a&lt;b&amp;c" in xml and "<authentication>open</authentication>" in xml
