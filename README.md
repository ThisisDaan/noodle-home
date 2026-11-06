# Noodle

A self-hosted smart home hub. It connects the devices you already have (Zigbee, Matter and Thread, Philips Hue, LIFX, Bluetooth sensors), shows them in one interface, and runs automations that are **plain YAML files**: edit them by hand, in the visual editor, or ask an AI to write them.

- **Your devices in one place:** a dashboard you arrange yourself, a device list, history graphs, rooms, and a phone app for Android.
- **Automations as files:** every flow is a small YAML file you can read, review, version and share. New flows always start switched off.
- **AI-friendly:** one button copies a prompt with your real devices and every available node; paste the AI's answer back and it is checked before it is added.
- **Pick only what you use:** each integration is a plugin you add in the setup wizard. Nothing is required, and Docker is optional.
- **Free software:** GPL-3.0-or-later.

## Install

Noodle (the `noodle/` folder) does not need the rest of this repository. It talks to the services you already have, and you add only the ones you use in the setup wizard.

**With Docker** (Linux; it needs the host network to find devices):

```bash
git clone https://github.com/ThisisDaan/noodle-home.git
cd noodle-home/noodle
docker compose up -d --build
```

Open `http://<this machine>:8090`. Your data and settings are in `noodle/data/` (flows are plain files in `data/config/flows/`).

**Updating:** `noodle/compose.yaml` uses the published image `ghcr.io/thisisdaan/noodle` (pushed by the release workflow when a `v*` tag is created). On the System page, *Check for updates* looks at the latest GitHub release and *Update* pulls the new image and restarts Noodle into it (needs the Docker socket mount). Building from source instead: `docker compose up -d --build`.

**With pip** (Python 3.11 or newer):

```bash
./noodle/build-wheel.sh                 # builds the interface and a wheel (needs bun and `pip install build`)
python3 -m venv /opt/noodle/venv
/opt/noodle/venv/bin/pip install noodle/backend/dist/noodle_home-*.whl
NOODLE_DATA=$HOME/noodle-data /opt/noodle/venv/bin/noodle
```

To keep it running, copy `noodle/noodle.service` to `/etc/systemd/system/`, edit the user and paths in it and run `sudo systemctl enable --now noodle`. Bluetooth sensors need BlueZ on the machine. `noodle --help` lists the other commands (`noodle validate`, `noodle schema`).

After the first login a short setup wizard asks for your home's name and location, which services you use, and helps pair a first device. Every step can be skipped.

## Integrations

Zigbee (through Zigbee2MQTT), Matter and Thread (python-matter-server and an OpenThread border router), Philips Hue (found and paired from the app), LIFX, Shelly, WLED, TP-Link Kasa, Philips WiZ, Yeelight, Govee, Roku, Yamaha MusicCast, Nanoleaf and Sonos (found on the network or added by IP address, no cloud), IKEA DIRIGERA (paired with its button), Pi-hole (ad blocking switch and stats), UniFi presence (who is on your Wi-Fi), Tasmota, ESPHome and other MQTT devices (Home Assistant discovery format), Home Assistant (bring in what it controls), Bluetooth temperature and humidity sensors, ntfy and in-app phone notifications, and Google speakers (speak). Heating is a flow: the Thermostat node watches a room sensor and switches a heater plug. Writing a new one is a single module, see "Writing an integration" below.

## Flows as files

Every automation is a YAML file in `<data>/config/flows/` (in Docker: `/data/config/flows/`). Edit them by hand or with an AI; the app reloads a changed file within a couple of seconds, and the visual editor writes the same files (your comments are kept). A flow that is new to the app always starts switched off.

Example flows (a blanket and a heater with safety cut-offs) are in `noodle/backend/noodle/examples/flows/`: copy one into that folder and change the device ids to yours.

```bash
noodle validate    # check all flow files
noodle schema      # JSON Schema of the format, with the nodes you have installed
```

In Docker: `docker compose exec noodle python -m noodle validate`. `GET /api/flow/schema` serves the same schema; device ids for `device_id` come from `GET /api/devices`. Format and an example: `noodle/backend/noodle/flowfiles.py`. Letting an AI write flows is described in [docs/AI.md](docs/AI.md).

## Custom devices and cards

**Custom devices.** Devices page, *New custom device*: make a device of your own with the things it should remember, each an
on/off, a number (with a unit and optionally a lowest, highest and step) or text. An automation fills them in with the
**Write to entity** step, and they work like any other device: you see them on the Devices page, other automations react to
them with *Device changes* and checks, and they can be put on the dashboard. The old flow variables are the text fields of a
built-in *Variables* device now (*Set variable* and *Check variable* keep working).

**Cards.** Every device can have a designed card: open the device and press *Design the card*. Pick a size (small, wide or
large), tap a slot and choose a component and which field it uses:

| Size | Slots |
|---|---|
| Small (today's tile) | 2 |
| Wide (two tiles wide) | 4 |
| Large (two wide, two high) | 12 |

| Component | Takes | For |
|---|---|---|
| Switch | 1 | something that can be on or off |
| Value | 1 | any reading or text |
| Dial (− and +) | 2 | a number, or a thermostat's target |
| Slider | 1 | a number, or a light's brightness |
| Graph | 2 x 2 | the last hours of a number |

Every card is made of these components, a designed one and a device's own look alike (a light is a power button and a brightness bar, a plug a power button and its power draw, a sensor its readings), so the designer always opens on exactly what is on the card and you change it from there. Only a remote's buttons have a look of their own that is not made of components yet. The designs are kept in `dashboard.yaml` under `cards`.

## Other config files

Next to `flows/` in `<data>/config/`, all YAML, all editable by hand (the app picks up an edit within a couple of seconds and keeps your comments when it saves):

| File | Holds |
|---|---|
| `settings.yaml` | one section per integration (`zigbee:`, `hue:`, ...) and the list of added integrations |
| `secrets.yaml` | Hue key and ntfy topic, readable by the owner only (keep it out of git) |
| `dashboard.yaml` | the dashboard cards, rooms order, hidden and pinned devices, tile order, device list options |
| `areas.yaml` | your rooms, and the name and room you gave each device |
| `hue-hooks.yaml` | only for an older Hue Tap/Dimmer setup forwarded through Home Assistant (see `noodle/backend/noodle/examples/hue-hooks.yaml`) |

Changing a setting restarts just the integration it belongs to. Clearing a device name by hand needs a restart to show the original name again. The database (`noodle.db`) holds only runtime state: history, timers and the login.

Environment variables are `NOODLE_DATA`, `NOODLE_CONFIG`, `NOODLE_PORT`, `NOODLE_EXTRA_PORT`, `NOODLE_URL`, `NOODLE_LAT`, `NOODLE_LON`, `NOODLE_TZ` and `NOODLE_AUTOMATIONS` (`0` stops flows running, for development). The older `HOMEPI_*` names still work.

## Writing an integration

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

### Finding devices

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

## Develop

Backend: `cd noodle/backend && pip install -r requirements-dev.txt && pytest`, and run it with `NOODLE_DATA=./dev-data python -m noodle`. Frontend: `cd noodle/frontend && bun install && bun run dev` (it proxies `/api` to port 8090), `bun run check` for types. To point a local hub at services elsewhere, set the addresses in the app (Integrations) or with `MQTT_HOST`, `MATTER_URL` and `OTBR_URL`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Noodle is free software under the [GNU General Public License v3.0 or later](LICENSE): you may use, study, change and share it, and anyone who shares a modified version must share it under the same licence, so it stays open for everyone. Contributions are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md).
