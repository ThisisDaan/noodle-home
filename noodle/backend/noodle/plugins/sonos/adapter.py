"""Sonos speakers over their local UPnP API (port 1400). No cloud, no account.

Each speaker gets a play/pause switch, a volume number and a mute switch. Volume works on the speaker itself; a
speaker that is part of a group still plays what the group plays.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

from ...hub import Device, Entity
from ..lan.adapter import LanAdapter

PORT = 1400
RENDERING = ("/MediaRenderer/RenderingControl/Control", "urn:schemas-upnp-org:service:RenderingControl:1")
TRANSPORT = ("/MediaRenderer/AVTransport/Control", "urn:schemas-upnp-org:service:AVTransport:1")


def envelope(service: str, action: str, args: dict[str, str]) -> str:
    body = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in args.items())
    return ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{service}">{body}</u:{action}></s:Body></s:Envelope>')


def tag(xml: str, name: str) -> str | None:
    m = re.search(rf"<{name}>(.*?)</{name}>", xml, re.S)
    return m.group(1) if m else None


class SonosAdapter(LanAdapter):
    source = "sonos"
    manufacturer = "Sonos"
    setting, attr = "sonos_devices", "SONOS_DEVICES"
    mdns = ("_sonos._tcp.local.",)
    poll_every = 6.0

    async def _soap(self, host: str, control: tuple[str, str], action: str, args: dict[str, str]) -> str:
        path, service = control
        res = await self.http.post(f"http://{host}:{PORT}{path}", content=envelope(service, action, args),
                                   headers={"Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": f'"{service}#{action}"'})
        res.raise_for_status()
        return res.text

    async def _description(self, host: str) -> str:
        res = await self.http.get(f"http://{host}:{PORT}/xml/device_description.xml")
        res.raise_for_status()
        if "Sonos" not in res.text:
            raise ValueError("not a Sonos speaker")
        return res.text

    async def identify(self, host):
        xml = await self._description(host)
        udn = (tag(xml, "UDN") or host).removeprefix("uuid:")
        return udn.lower(), tag(xml, "roomName") or tag(xml, "friendlyName") or "Sonos"

    async def read(self, key, host):
        xml = await self._description(host)
        volume = await self._soap(host, RENDERING, "GetVolume", {"InstanceID": 0, "Channel": "Master"})
        mute = await self._soap(host, RENDERING, "GetMute", {"InstanceID": 0, "Channel": "Master"})
        transport = await self._soap(host, TRANSPORT, "GetTransportInfo", {"InstanceID": 0})
        playing = tag(transport, "CurrentTransportState") in ("PLAYING", "TRANSITIONING")
        entities = {
            "playing": Entity("playing", "switch", "Playing", state=playing),
            "volume": Entity("volume", "number", "Volume", state=int(tag(volume, "CurrentVolume") or 0), unit="%",
                             attrs={"min": 0, "max": 100, "step": 1}),
            "mute": Entity("mute", "switch", "Muted", state=tag(mute, "CurrentMute") == "1"),
        }
        return Device(id=f"sonos:{key}", source=self.source, name=tag(xml, "roomName") or "Sonos",
                      model=tag(xml, "modelName"), manufacturer=self.manufacturer, entities=entities)

    async def send(self, device, entity, host, on, brightness, toggle, **extra):
        if entity.key == "volume":
            value = extra.get("value")
            if value is None:
                return
            await self._soap(host, RENDERING, "SetVolume", {"InstanceID": 0, "Channel": "Master",
                                                            "DesiredVolume": max(0, min(100, round(value)))})
        elif entity.key == "mute":
            want = (not entity.state) if toggle else on
            if want is not None:
                await self._soap(host, RENDERING, "SetMute", {"InstanceID": 0, "Channel": "Master", "DesiredMute": int(want)})
        elif entity.key == "playing":
            want = (not entity.state) if toggle else on
            if want is True:
                await self._soap(host, TRANSPORT, "Play", {"InstanceID": 0, "Speed": 1})
            elif want is False:
                await self._soap(host, TRANSPORT, "Pause", {"InstanceID": 0})
