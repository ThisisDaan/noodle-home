"""Putting a brand-new Shelly on the home Wi-Fi, so the user never has to do it by hand.

A Shelly that was never set up (or was reset) opens its own open Wi-Fi network, named like `shelly1-A4CF12B3C4D5`
or `ShellyPlus1PM-...`, and answers at 192.168.33.1. To set it up, this machine joins that network for a moment
(NetworkManager's `nmcli` on Linux, `netsh wlan` on Windows), tells the Shelly the home network's name and password,
goes back to its own network and waits for the Shelly to announce itself there. Gen1 (no Bluetooth) and newer
Shellies both work.

It only happens while the user is adding a Shelly: the nearby networks are listed once per Search, nothing scans
in the background. The Wi-Fi password goes to the Shelly and is never stored or logged.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import socket
import sys
import tempfile
import time
from xml.sax.saxutils import escape
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

SETUP_ADDRESS = "192.168.33.1"  # where every Shelly answers on its own network
CONNECTION = "noodle-shelly-setup"  # the temporary NetworkManager connection, deleted again afterwards

REACH_SECONDS = 30  # how long the Shelly gets to answer once this machine is on its network

NO_NMCLI = "this machine's Wi-Fi is not run by NetworkManager"
NO_WIFI = "this machine has no Wi-Fi"
LOCATION = ("Windows only shows Wi-Fi networks to apps that may use your location. Turn on Settings > Privacy & "
            "security > Location, and 'Let desktop apps access your location' on the same page, then search again")
NOT_ALLOWED = ("Noodle is not allowed to change this machine's Wi-Fi. Allow it once (see Shelly in "
               "docs/integrations.md), or set the Shelly up by hand")
LOCKED = ("This Shelly has a password set. Reset it (hold its button for about 10 seconds), then search again")


class WifiError(RuntimeError):
    """The Wi-Fi tool is missing, not allowed, or failed. The message is a sentence for the user."""


@dataclass
class Network:
    ssid: str
    freq: int = 0  # MHz; 0 when nmcli did not say
    signal: int = 0
    in_use: bool = False


def split_terse(line: str) -> list[str]:
    """One line of `nmcli -t` output: fields split on ':', where a ':' or '\\' inside a value is escaped."""
    out, cur, escaped = [], [], False
    for ch in line:
        if escaped:
            cur.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


_AP = re.compile(r"^shelly[a-z0-9]*(-[a-z0-9]+)*-[0-9a-f]{6,12}$", re.IGNORECASE)


def is_shelly_ap(ssid: str) -> bool:
    """The network a Shelly opens while it is not set up yet: 'shelly1-A4CF12', 'shellyplug-s-7C87CE', ..."""
    return bool(_AP.match(ssid))


def ap_name(ssid: str) -> str:
    """'shellyplug-s-7C87CE' -> 'Shelly plug-s', 'ShellyPlus1PM-...' -> 'Shelly Plus1PM'."""
    model = ssid.rsplit("-", 1)[0][len("shelly"):].strip("-")
    return f"Shelly {model}" if model else "Shelly"


def is_24(freq: int) -> bool:
    return 0 < freq < 3000


def parse_networks(text: str) -> list[Network]:
    """`nmcli -t -f SSID,FREQ,SIGNAL,IN-USE device wifi list` -> one Network per name (the strongest one)."""
    nets = []
    for line in text.splitlines():
        parts = split_terse(line)
        if len(parts) < 4 or not parts[0]:
            continue
        ssid, freq, signal, in_use = parts[0], parts[1], parts[2], parts[3]
        nets.append(Network(ssid, int(freq.split()[0]) if freq.split() and freq.split()[0].isdigit() else 0,
                            int(signal) if signal.isdigit() else 0, in_use.strip() == "*"))
    return merge(nets)


def merge(nets: list[Network]) -> list[Network]:
    """One Network per name: in use if any is, 2.4 GHz if it is heard there at all, the strongest signal."""
    best: dict[str, Network] = {}
    for net in nets:
        ssid = net.ssid
        old = best.get(ssid)
        if old is None:
            best[ssid] = net
            continue
        old.in_use = old.in_use or net.in_use
        if (is_24(net.freq) or not old.freq) and not is_24(old.freq):  # keep 2.4 GHz once heard: a Shelly needs it
            old.freq = net.freq
        old.signal = max(old.signal, net.signal)
    return sorted(best.values(), key=lambda n: (not n.in_use, -n.signal))


def explain(text: str) -> str:
    low = text.lower()
    if "location" in low and ("permission" in low or "privacy" in low):
        return LOCATION
    if "no wireless interface" in low or "wlansvc" in low:
        return NO_WIFI
    if "not authorized" in low or "insufficient privileges" in low or "permission denied" in low:
        return NOT_ALLOWED
    if "no network with ssid" in low:
        return "The Shelly's Wi-Fi is out of range of this machine. Move them closer, then search again"
    if "secrets were required" in low or "802-1x" in low:
        return "The Shelly's Wi-Fi asked for a password, so this is not a Shelly waiting to be set up"
    return text.strip().removeprefix("Error: ") or "nmcli failed"


Run = Callable[[list[str]], Awaitable[str]]


async def run_nmcli(args: list[str]) -> str:
    if shutil.which("nmcli") is None:
        raise WifiError(NO_NMCLI)
    proc = await asyncio.create_subprocess_exec("nmcli", *args, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), 60)
    except asyncio.TimeoutError:
        proc.kill()
        raise WifiError("The Wi-Fi did not answer in time")
    if proc.returncode:
        raise WifiError(explain(err.decode(errors="replace") or out.decode(errors="replace")))
    return out.decode(errors="replace")


class NmcliWifi:
    """This machine's Wi-Fi on Linux, through NetworkManager's nmcli. `run` is replaceable for the tests."""

    def __init__(self, run: Run = run_nmcli) -> None:
        self.run = run

    async def devices(self) -> list[tuple[str, str, str]]:
        """(device, type, state) for every network device."""
        out = await self.run(["-t", "-f", "DEVICE,TYPE,STATE", "device"])
        return [tuple(p[:3]) for p in map(split_terse, out.splitlines()) if len(p) >= 3]  # type: ignore[misc]

    async def device(self) -> str:
        for name, kind, state in await self.devices():
            if kind == "wifi" and state != "unavailable":
                return name
        raise WifiError(NO_WIFI)

    async def wired(self) -> bool:
        """Connected by cable as well, so switching the Wi-Fi does not take the hub off the network."""
        return any(kind == "ethernet" and state.startswith("connected") for _, kind, state in await self.devices())

    async def scan(self, device: str, fresh: bool = True) -> list[Network]:
        args = ["-t", "-f", "SSID,FREQ,SIGNAL,IN-USE", "device", "wifi", "list", "ifname", device, "--rescan"]
        try:
            out = await self.run(args + ["yes" if fresh else "no"])
        except WifiError as err:
            if str(err) in (NO_NMCLI, NOT_ALLOWED):
                raise
            out = await self.run(args + ["no"])  # "scanning not allowed" right after another scan: use what it knows
        return parse_networks(out)

    async def active(self, device: str) -> str | None:
        """The connection the Wi-Fi device is on now (its uuid), to go back to afterwards."""
        out = await self.run(["-t", "-f", "UUID,DEVICE", "connection", "show", "--active"])
        for parts in map(split_terse, out.splitlines()):
            if len(parts) >= 2 and parts[1] == device:
                return parts[0]
        return None

    async def join(self, device: str, ssid: str) -> None:
        await self.forget()  # one left over from a setup that was cut short
        await self.run(["--wait", "40", "device", "wifi", "connect", ssid, "ifname", device, "name", CONNECTION])

    async def forget(self) -> None:
        try:
            await self.run(["connection", "delete", "id", CONNECTION])
        except WifiError:
            pass

    async def leave(self, back: str | None) -> None:
        await self.forget()
        if back:
            try:
                await self.run(["--wait", "40", "connection", "up", "uuid", back])
            except WifiError:
                pass  # NetworkManager reconnects by itself as well


async def configure(http: httpx.AsyncClient, ssid: str, password: str) -> str:
    """Tell the Shelly at SETUP_ADDRESS to join `ssid`. Returns its key (the MAC, as the Shelly adapter keys it)."""
    base = f"http://{SETUP_ADDRESS}"
    end = time.monotonic() + REACH_SECONDS
    while True:  # right after joining, the address may take a few seconds to arrive
        try:
            res = await http.get(f"{base}/shelly")
            res.raise_for_status()
            about = res.json()
            break
        except (httpx.HTTPError, ValueError) as err:
            if time.monotonic() >= end:
                raise ValueError(f"The Shelly did not answer on its own Wi-Fi ({err.__class__.__name__})") from err
            await asyncio.sleep(1)
    if not isinstance(about, dict) or "mac" not in about:
        raise ValueError("That network is not a Shelly")
    if about.get("auth") or about.get("auth_en"):
        raise ValueError(LOCKED)
    key = str(about["mac"]).lower().replace(":", "")
    if int(about.get("gen") or 1) >= 2:
        res = await http.post(f"{base}/rpc", json={"id": 1, "src": "noodle", "method": "WiFi.SetConfig", "params": {
            "config": {"sta": {"ssid": ssid, "pass": password, "enable": True}}}})
        if res.status_code == 401:
            raise ValueError(LOCKED)
        res.raise_for_status()
        if isinstance(body := res.json(), dict) and body.get("error"):
            raise ValueError(f"The Shelly refused the Wi-Fi details: {body['error'].get('message', body['error'])}")
        return key
    # Gen1: a form POST, so the password is not in a URL (and never in a log line).
    data = {"enabled": "1", "ssid": ssid}
    if password:
        data["key"] = password
    try:
        res = await http.post(f"{base}/settings/sta", data=data)
    except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ReadTimeout):
        return key  # it may switch networks before it finishes answering
    if res.status_code == 401:
        raise ValueError(LOCKED)
    res.raise_for_status()
    return key


# --- Windows: netsh wlan

PROFILE_KEYS = {"profile", "profiel", "profil", "perfil", "profilo"}  # the label is translated with Windows
_KV = re.compile(r"^\s*(.+?)\s+:\s?(.*?)\s*$")


def _decode(data: bytes) -> str:
    try:
        return data.decode("oem")  # netsh writes in the console code page
    except (LookupError, UnicodeDecodeError):
        return data.decode(errors="replace")


async def run_netsh(args: list[str]) -> str:
    proc = await asyncio.create_subprocess_exec("netsh", *args, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), 30)
    except asyncio.TimeoutError:
        proc.kill()
        raise WifiError("The Wi-Fi did not answer in time")
    text = _decode(out) + _decode(err)
    if proc.returncode:
        raise WifiError(explain(text))
    return text


def parse_interfaces(text: str) -> list[dict[str, str]]:
    """`netsh wlan show interfaces` -> one dict per Wi-Fi interface: name, ssid (when connected), profile."""
    out = []
    for chunk in re.split(r"\n\s*\n", text.replace("\r", "")):
        pairs = [(m.group(1).strip(), m.group(2)) for line in chunk.splitlines() if (m := _KV.match(line))]
        if len(pairs) < 3:
            continue
        info = {"name": pairs[0][1]}  # the first line is the name, whatever the language
        for key, value in pairs:
            if key == "SSID":
                info["ssid"] = value
            elif key.lower() in PROFILE_KEYS:
                info["profile"] = value
        out.append(info)
    return out


def parse_netsh_networks(text: str, current: str | None = None) -> list[Network]:
    """`netsh wlan show networks mode=bssid` -> the networks, with the band of each access point."""
    nets: list[Network] = []
    ssid: str | None = None
    for line in text.replace("\r", "").splitlines():
        if m := re.match(r"^SSID \d+\s*:\s?(.*?)\s*$", line):
            ssid = m.group(1)
            if ssid:
                nets.append(Network(ssid, in_use=ssid == current))
            continue
        if not ssid or not (m := _KV.match(line)):
            continue
        key, value = m.group(1).strip().lower(), m.group(2)
        net = nets[-1]
        if band := re.match(r"^(\d+)(?:[.,]\d+)?\s*GHz$", value):
            freq = {"2": 2437, "5": 5180, "6": 5955}.get(band.group(1), 0)
        elif value.isdigit() and key.startswith(("chan", "kana", "canal", "kanal")):
            freq = 2407 + 5 * int(value) if int(value) <= 14 else 5000 + 5 * int(value)
        elif pct := re.match(r"^(\d+)%$", value):
            net.signal = max(net.signal, int(pct.group(1)))
            continue
        else:
            continue
        if not is_24(net.freq):  # one network can be on both bands: keep 2.4 GHz once heard
            net.freq = freq
    return merge(nets)


def _profile_xml(ssid: str) -> str:
    return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{CONNECTION}</name>
  <SSIDConfig><SSID><name>{escape(ssid)}</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM><security><authEncryption><authentication>open</authentication><encryption>none</encryption>
  <useOneX>false</useOneX></authEncryption></security></MSM>
</WLANProfile>
"""


class NetshWifi:
    """This machine's Wi-Fi on Windows, through `netsh wlan`. Windows must allow apps to use the location before
    it lists networks (Settings > Privacy & security > Location). `run` is replaceable for the tests."""

    def __init__(self, run: Run = run_netsh) -> None:
        self.run = run
        self._device = ""

    async def _interface(self, device: str | None = None) -> dict[str, str]:
        for info in parse_interfaces(await self.run(["wlan", "show", "interfaces"])):
            if device is None or info["name"] == device:
                return info
        raise WifiError(NO_WIFI)

    async def device(self) -> str:
        self._device = (await self._interface())["name"]
        return self._device

    async def wired(self) -> bool:
        """The hub reaches the network some other way than this Wi-Fi (a cable)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("192.0.2.1", 9))  # sends nothing: only asks which address the route goes out from
                mine = s.getsockname()[0]
            text = await self.run(["interface", "ipv4", "show", "addresses", f"name={self._device or await self.device()}"])
        except (OSError, WifiError):
            return False
        return mine not in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text)

    async def scan(self, device: str, fresh: bool = True) -> list[Network]:
        self._device = device
        current = (await self._interface(device)).get("ssid")
        text = await self.run(["wlan", "show", "networks", "mode=bssid", f"interface={device}"])
        if "SSID" not in text and "location" in text.lower():
            raise WifiError(LOCATION)
        return parse_netsh_networks(text, current)

    async def active(self, device: str) -> str | None:
        info = await self._interface(device)
        return info.get("profile") or info.get("ssid")

    async def join(self, device: str, ssid: str) -> None:
        self._device = device
        await self.forget()
        fd, path = tempfile.mkstemp(suffix=".xml")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_profile_xml(ssid))
            await self.run(["wlan", "add", "profile", f"filename={path}", f"interface={device}", "user=current"])
        finally:
            os.unlink(path)
        await self.run(["wlan", "connect", f"name={CONNECTION}", f"ssid={ssid}", f"interface={device}"])
        end = time.monotonic() + 30
        while time.monotonic() < end:  # netsh returns at once: wait until Windows is on the Shelly's network
            if (await self._interface(device)).get("ssid") == ssid:
                return
            await asyncio.sleep(1)
        raise WifiError("Could not join the Shelly's Wi-Fi. Move it closer to this machine, then search again")

    async def forget(self) -> None:
        try:
            await self.run(["wlan", "delete", "profile", f"name={CONNECTION}"]
                           + ([f"interface={self._device}"] if self._device else []))
        except WifiError:
            pass

    async def leave(self, back: str | None) -> None:
        await self.forget()
        if back and back != CONNECTION:
            try:
                await self.run(["wlan", "connect", f"name={back}"] + ([f"interface={self._device}"] if self._device else []))
            except WifiError:
                pass  # Windows reconnects to a known network by itself as well


def system_wifi():
    """The Wi-Fi of this machine: netsh on Windows, NetworkManager elsewhere."""
    return NetshWifi() if sys.platform == "win32" else NmcliWifi()
