"""Putting a brand-new Shelly on the home Wi-Fi, so the user never has to do it by hand.

A Shelly that was never set up (or was reset) opens its own open Wi-Fi network, named like `shelly1-A4CF12B3C4D5`
or `ShellyPlus1PM-...`, and answers at 192.168.33.1. To set it up, this machine joins that network for a moment
(through NetworkManager's `nmcli`), tells the Shelly the home network's name and password, goes back to its own
network and waits for the Shelly to announce itself there. Gen1 (no Bluetooth) and newer Shellies both work.

It only happens while the user is adding a Shelly: the nearby networks are listed once per Search, nothing scans
in the background. The Wi-Fi password goes to the Shelly and is never stored or logged.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

SETUP_ADDRESS = "192.168.33.1"  # where every Shelly answers on its own network
CONNECTION = "noodle-shelly-setup"  # the temporary NetworkManager connection, deleted again afterwards

NO_NMCLI = "this machine's Wi-Fi is not run by NetworkManager"
NOT_ALLOWED = ("Noodle is not allowed to change this machine's Wi-Fi. Allow it once (see Shelly in "
               "docs/integrations.md), or set the Shelly up by hand")
LOCKED = ("This Shelly has a password set. Reset it (hold its button for about 10 seconds), then search again")


class NmcliError(RuntimeError):
    """nmcli is missing, not allowed, or failed. The message is a sentence for the user."""


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


def parse_networks(text: str) -> list[Network]:
    """`nmcli -t -f SSID,FREQ,SIGNAL,IN-USE device wifi list` -> one Network per name (the strongest one)."""
    best: dict[str, Network] = {}
    for line in text.splitlines():
        parts = split_terse(line)
        if len(parts) < 4 or not parts[0]:
            continue
        ssid, freq, signal, in_use = parts[0], parts[1], parts[2], parts[3]
        net = Network(ssid, int(freq.split()[0]) if freq.split() and freq.split()[0].isdigit() else 0,
                      int(signal) if signal.isdigit() else 0, in_use.strip() == "*")
        old = best.get(ssid)
        if old is None:
            best[ssid] = net
            continue
        old.in_use = old.in_use or net.in_use
        if net.freq and net.freq < 3000:  # remember that the name is on 2.4 GHz, the only band a Shelly can join
            old.freq = net.freq if not old.freq or old.freq >= 3000 else old.freq
        old.signal = max(old.signal, net.signal)
    return sorted(best.values(), key=lambda n: (not n.in_use, -n.signal))


def explain(text: str) -> str:
    low = text.lower()
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
        raise NmcliError(NO_NMCLI)
    proc = await asyncio.create_subprocess_exec("nmcli", *args, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), 60)
    except asyncio.TimeoutError:
        proc.kill()
        raise NmcliError("The Wi-Fi did not answer in time")
    if proc.returncode:
        raise NmcliError(explain(err.decode(errors="replace") or out.decode(errors="replace")))
    return out.decode(errors="replace")


class Wifi:
    """This machine's Wi-Fi, through nmcli. `run` is replaceable for the tests."""

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
        raise NmcliError("this machine has no Wi-Fi")

    async def wired(self) -> bool:
        """Connected by cable as well, so switching the Wi-Fi does not take the hub off the network."""
        return any(kind == "ethernet" and state.startswith("connected") for _, kind, state in await self.devices())

    async def scan(self, device: str) -> list[Network]:
        args = ["-t", "-f", "SSID,FREQ,SIGNAL,IN-USE", "device", "wifi", "list", "ifname", device, "--rescan"]
        try:
            out = await self.run(args + ["yes"])
        except NmcliError as err:
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
        except NmcliError:
            pass

    async def leave(self, back: str | None) -> None:
        await self.forget()
        if back:
            try:
                await self.run(["--wait", "40", "connection", "up", "uuid", back])
            except NmcliError:
                pass  # NetworkManager reconnects by itself as well


async def configure(http: httpx.AsyncClient, ssid: str, password: str) -> str:
    """Tell the Shelly at SETUP_ADDRESS to join `ssid`. Returns its key (the MAC, as the Shelly adapter keys it)."""
    base = f"http://{SETUP_ADDRESS}"
    try:
        res = await http.get(f"{base}/shelly")
        res.raise_for_status()
        about = res.json()
    except (httpx.HTTPError, ValueError) as err:
        raise ValueError(f"The Shelly did not answer on its own Wi-Fi ({err.__class__.__name__})") from err
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
