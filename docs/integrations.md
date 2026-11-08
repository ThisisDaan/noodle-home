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

Before opening a pull request, see [CONTRIBUTING.md](../CONTRIBUTING.md).
