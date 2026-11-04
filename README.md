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

Zigbee (through Zigbee2MQTT), Matter and Thread (python-matter-server and an OpenThread border router), Philips Hue (paired from the app), LIFX (found on the network, no cloud), Bluetooth temperature and humidity sensors, ntfy and in-app phone notifications, Google speakers (speak), and Docker containers (restart and logs). Heating is a flow: the Thermostat node watches a room sensor and switches a heater plug. Writing a new one is a single module, see "Writing an integration" below.

## Flows as files

Every automation is a YAML file in `<data>/config/flows/` (in Docker: `/data/config/flows/`). Edit them by hand or with an AI; the app reloads a changed file within a couple of seconds, and the visual editor writes the same files (your comments are kept). A flow that is new to the app always starts switched off.

Example flows (a blanket and a heater with safety cut-offs) are in `noodle/backend/noodle/examples/flows/`: copy one into that folder and change the device ids to yours.

```bash
noodle validate    # check all flow files
noodle schema      # JSON Schema of the format, with the nodes you have installed
```

In Docker: `docker compose exec noodle python -m noodle validate`. `GET /api/flow/schema` serves the same schema; device ids for `device_id` come from `GET /api/devices`. Format and an example: `noodle/backend/noodle/flowfiles.py`. Letting an AI write flows is described in [docs/AI.md](docs/AI.md).

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

Each integration is one module in `noodle/backend/noodle/plugins/` with a module-level `PLUGIN`. Nothing else has to change: the Integrations page, start-up, settings files, flow editor and System page are built from the plugins.

```python
from ..adapters.mything import MyThingAdapter      # talks to the service, has .source and async run()
from .base import Field, Node, NodeField, Plugin


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

Optional hooks: `preset()` (already set up counts as added), `routes()` (own API endpoints), `details()` and `panel` (extra panel on the page, a component listed in `frontend/src/lib/integrations/panels.ts`), `system_info()` (shown on the System page), `forget` and `on_remove()` (cleanup when removed). Add the setting keys to `SETTINGS` in `config.py` with the plugin id as section. The tests in `noodle/backend/tests` check that the pieces agree (`pip install -r requirements-dev.txt`, then `pytest`).

## Develop

Backend: `cd noodle/backend && pip install -r requirements-dev.txt && pytest`, and run it with `NOODLE_DATA=./dev-data python -m noodle`. Frontend: `cd noodle/frontend && bun install && bun run dev` (it proxies `/api` to port 8090), `bun run check` for types. To point a local hub at services elsewhere, set the addresses in the app (Integrations) or with `MQTT_HOST`, `MATTER_URL` and `OTBR_URL`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Noodle is free software under the [GNU General Public License v3.0 or later](LICENSE): you may use, study, change and share it, and anyone who shares a modified version must share it under the same licence, so it stays open for everyone. Contributions are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md).
