# Writing an integration

Each integration is one folder in `noodle/backend/noodle/plugins/`, and everything about it lives there:

```
plugins/mything/
    __init__.py     # from .plugin import PLUGIN
    plugin.py       # what it is: name, help text, settings fields, status, flow nodes, search
    adapter.py      # how it works: talks to the device or service
```

Outside the folder only its setting keys in `config.SETTINGS` have to be added (and a panel in `panels.ts` if it has a custom one): the Integrations page, start-up, settings files, flow editor and System page are built from the plugins. For a device with a local HTTP API, the adapter extends `LanAdapter` and the plugin extends `LanPlugin` (see `plugins/wled/`, about 70 lines in total).

`plugin.py`:

```python
from .adapter import MyThingAdapter                # talks to the service, has .source and async run()
from ..base import Field, Node, NodeField, Plugin


async def run_beep(n):                              # what the flow node does
    await n.hub.adapters["mything"].beep(n.fill(n.data.get("text")))
    n.log("Beeped")
    await n.follow()                                # carry on with the next nodes


class MyThingPlugin(Plugin):
    id = "mything"                                  # section name in settings.yaml
    source = "mything"                              # the adapter's source
    adapter_class = MyThingAdapter
    name = "My thing"
    help = "One or two sentences shown on the Integrations page."
    fields = [Field("mything_host", "Address", "192.168.1.30")]   # also add the key to config.SETTINGS
    icon = "plug"
    gated = True                                    # only runs once the user has added it
    order = 60

    def status(self, adapter):                      # True connected, False not, None unknown
        return adapter.connected

    def nodes(self):                                # optional: nodes for the flow editor and the YAML schema
        return [Node("action.beep", "Beep", "action", run_beep, summary="{text}", defaults={"text": "hi"},
                     fields=[NodeField("text", "Text")])]


PLUGIN = MyThingPlugin()
```

`support = "supported"` or `"untested"` sets the badge on the Integrations page; leave it as `untested` (the default) until someone has run it on real devices.

Optional hooks: `preset()` (already set up counts as added), `routes()` (own API endpoints), `details()` and `panel` (extra panel on the page, a component listed in `frontend/src/lib/integrations/panels.ts`), `system_info()` (shown on the System page), `forget` and `on_remove()` (cleanup when removed). Add the setting keys to `SETTINGS` in `config.py` with the plugin id as section. The tests in `noodle/backend/tests` check that the pieces agree (`pip install -r requirements-dev.txt`, then `pytest`).

## Finding devices

Every integration adds devices the same way: a **Search** button that looks for 30 seconds, only when the user presses it, and a list of what it found with an Add button. Set `searchable = True` and implement two methods; the screen (radar, countdown, list) is shared and needs no code:

```python
    searchable = True
    noun = "My things"                              # "Looking for My things…"
    search_hint = "Hold the button on the thing."   # optional, shown while searching
    press_hint = "Press the button on the hub."     # optional, for tap-to-pair devices

    async def search(self, adapter, seconds, found):
        found("aa:bb", name="Kitchen thing", detail="192.168.1.31")     # call it for each thing, as it turns up

    async def add_found(self, adapter, key):
        if not await adapter.try_pair(key):
            raise PressButton("Press the button")   # the screen shows "press the button" and asks again for 30 s
        config.save({"mything_host": key})
```

Devices that join by themselves (Zigbee2MQTT opens its network for the search) are reported with `found(..., added=True)` and need no `add_found`. Set `restart_after_add = True` if `add_found` changed settings the adapter reads.

A device that first has to join the Wi-Fi is reported with `found(key, ..., wifi={"networks": [...], "current": "...", "offline": False})`. The screen then asks for the network (a dropdown of `networks`) and its password, and `add_found` gets them as `wifi_ssid` and `wifi_password`, with `report(text)` to show each step. Never store the password. A search can call `found.note(text)` to tell the user what it could not look for.

## Setting up new Shellies

A Shelly that is not on the Wi-Fi yet (new, or reset) opens its own network, `shelly1-…` or `ShellyPlus…-…`. Shelly's Search lists these as well. When the user picks one, enters the home Wi-Fi and presses Connect, the hub joins the Shelly's network for a few seconds, gives it the Wi-Fi details at 192.168.33.1 and goes back. Then it waits for the Shelly to show up on the home network and adds it (`plugins/shelly/hotspot.py`). This works for Gen1 (no Bluetooth) and newer Shellies alike.

What the hub needs:

- Wi-Fi, and the Shelly within reach of it. On Linux the Wi-Fi must be run by NetworkManager (`nmcli`), as on Raspberry Pi OS Bookworm and later. On Windows the hub uses `netsh wlan`. Windows only lists Wi-Fi networks to apps that may use the location, so turn on Settings > Privacy & security > Location and "Let desktop apps access your location". Windows also lists only the networks it heard last, so if a new Shelly does not show up, open the Wi-Fi list on the taskbar and search again.
- On Linux, permission to change the Wi-Fi. Running as the `noodle` user (`noodle.service`), allow it once:

  ```bash
  sudo tee /etc/polkit-1/rules.d/50-noodle-wifi.rules <<'RULES'
  polkit.addRule(function (action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 && subject.user === "noodle") return polkit.Result.YES;
  });
  RULES
  ```

- A cable connection is best. A hub that is only on Wi-Fi leaves the network for about a minute while it does this. The page says so beforehand (unless it is open on the hub itself), and the setup carries on.

Without these, Search still finds Shellies already on the network and explains how to set up a new one by hand.

Before opening a pull request, see [CONTRIBUTING.md](../CONTRIBUTING.md).
