"""Home Assistant as a source of devices (see adapter.py)."""


from ... import config
from .adapter import MDNS, HomeAssistantAdapter, found_url
from ..base import Field, Plugin


class HomeAssistantPlugin(Plugin):
    id = "homeassistant"
    source = "homeassistant"
    adapter_class = HomeAssistantAdapter
    name = "Home Assistant"
    help = ("Bring in the lights, switches, fans, blinds, locks and sensors your Home Assistant controls, for "
            "everything Noodle has no integration of its own for. Press Search to find it (or type its address), then make a "
            "token on your Home Assistant profile page (Security, Long-lived access tokens) and paste it in. A device that is also paired with Noodle directly would show up twice.")
    fields = [Field("ha_url", "Address", "http://homeassistant.local:8123"),
              Field("ha_token", "Long-lived access token", secret=True)]
    gated = True
    icon = "home"
    order = 42
    searchable = True
    search_finds = "hub"
    noun = "Home Assistants"
    search_hint = "Home Assistant has to be running on this network. You still make the access token yourself."
    restart_after_add = True
    found_urls: dict[str, str] = {}  # what a search found: key (the address without http://) -> full address
    forget = ["ha_url", "ha_token"]

    def details(self, adapter):
        return {"error": adapter.error}

    def preset(self):
        return bool(config.HA_URL and config.HA_TOKEN)

    async def search(self, adapter, seconds, found):
        from ... import mdns

        async def on_service(service_type, name, info) -> None:
            url = found_url(info.properties, info.parsed_addresses(), info.port)
            if url:
                key = url.split("://", 1)[-1]  # no slashes: the key travels in the address of the Add request
                self.found_urls[key] = url
                label = (info.properties.get(b"location_name") or b"").decode() or "Home Assistant"
                found(key, name=label, detail=url)

        await mdns.browse([MDNS], seconds, on_service)

    async def add_found(self, adapter, key):
        """Only the address is known; the token is made in Home Assistant and typed into the form afterwards."""
        config.save({"ha_url": self.found_urls.get(key) or f"http://{key}"})

    def on_remove(self, hub, adapter):
        super().on_remove(hub, adapter)
        adapter.entity_device.clear()


PLUGIN = HomeAssistantPlugin()
