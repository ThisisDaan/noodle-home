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

**From a published image** (once a release is tagged, the CI workflow pushes `ghcr.io/<owner>/noodle`): in `noodle/compose.yaml` replace `build: .` with `image: ghcr.io/<owner>/noodle:latest`.

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

Zigbee (through Zigbee2MQTT), Matter and Thread (python-matter-server and an OpenThread border router), Philips Hue (paired from the app), LIFX (found on the network, no cloud), Bluetooth temperature and humidity sensors, ntfy and in-app phone notifications, Google speakers (speak), a thermostat, and Docker containers (restart and logs). Writing a new one is a single module, see "Writing an integration" below.

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

---

# The full Raspberry Pi stack

This repository also holds the setup Noodle grew out of: a Raspberry Pi 4 running Mosquitto, Zigbee2MQTT, Home Assistant, a Thread border router, Matter, an optional UniFi controller and Noodle, all as plain Docker containers (`compose.yaml`). You do not need it to use Noodle.

## Setup

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. Set hostname, user, password and SSH under *Edit settings*.
2. Plug in the Zigbee stick, boot the Pi and give it a fixed IP in your router.
3. Get this repository onto the Pi and run the installer:

   ```bash
   ssh youruser@noodle.local
   git clone https://github.com/ThisisDaan/noodle-home.git
   cd noodle-home && ./install.sh
   ```

| Service | URL |
|---|---|
| Noodle | `http://noodle.local` or `http://<pi-ip>:8090` (needs the Pi's hostname set to `noodle`: `sudo hostnamectl set-hostname noodle`) |
| Home Assistant | `http://<pi-ip>:8123` |
| Zigbee2MQTT | `http://<pi-ip>:8081` |
| MQTT broker | `<pi-ip>:1883` |

## Restoring an old setup

If you already have a Zigbee2MQTT or Home Assistant setup, put its data in `backups/` (git-ignored) and copy it in after `install.sh` has run once, on the Pi:

```bash
docker compose down
cp -a backups/<zigbee2mqtt backup>/{configuration.yaml,database.db,coordinator_backup.json} data/zigbee2mqtt/
sudo cp -a backups/<home assistant backup>/data/. data/homeassistant/
docker compose up -d
```

- **Zigbee2MQTT:** its config should use `mqtt://mosquitto:1883`, and your stick is mapped to `/dev/ttyUSB0` by compose (the `zstack` adapter setting must match your stick).
- **Home Assistant:** an unprotected, extracted `/config` folder needs no restore wizard. If its MQTT integration points at an IP address, give the Pi that same IP (a fixed address in your router) or change it in Home Assistant.
- `install.sh` sets `ZIGBEE_DEVICE` in `.env` to your stick's stable path from `ls /dev/serial/by-id/`. If you have several USB devices, set it by hand.

## Everyday commands

```bash
docker compose up -d          # start / apply changes
docker compose pull && docker compose up -d   # update everything
docker compose logs -f zigbee2mqtt
./backup.sh                   # archive data/ and .env into backups/
```

## Thread (MG24 stick)

The `otbr` container is the Thread border router; `matter-server` handles the Matter devices that run over Thread.

1. **Flash OpenThread RCP firmware.** The stick ships with Zigbee firmware, which the border router can't use. On a PC, open the Sonoff web flasher (https://dongle.sonoff.tech/sonoff-dongle-flasher/) in Chrome or Edge and pick the *OpenThread RCP* firmware for the Dongle Plus MG24.
2. **Plug it into the Pi** and find its path with `ls /dev/serial/by-id/`. Put it in `.env` as `THREAD_DEVICE`, and set `THREAD_BACKBONE_IF` to `eth0` or `wlan0`.
3. **Enable IPv6 forwarding on the Pi** (one time):

   ```bash
   sudo tee /etc/sysctl.d/60-otbr.conf <<'EOF'
   net.ipv6.conf.all.disable_ipv6 = 0
   net.ipv4.conf.all.forwarding = 1
   net.ipv6.conf.all.forwarding = 1
   net.ipv6.conf.all.accept_ra_rt_info_max_plen = 64
   net.ipv6.conf.all.accept_ra = 2
   EOF
   sudo sysctl --system
   ```

4. `docker compose up -d`, then check `docker compose logs -f otbr` for errors.
5. In Noodle, add **Matter and Thread** under Integrations (Matter server `ws://127.0.0.1:5580/ws`, border router `http://127.0.0.1:8082`), then pair Matter devices on the System page with their setup code. If you also use Home Assistant: add **Open Thread Border Router** (`http://127.0.0.1:8082`), **Thread** and **Matter** (`ws://127.0.0.1:5580/ws`) there, and pair with its Companion app (your phone needs Bluetooth on and the same Wi-Fi).

`matter2mqtt` forwards Matter button events to MQTT (`matter/<node>/<endpoint>/<event>`) for Home Assistant's scroll wheel automation.

## Optional: UniFi controller

A UniFi access point needs a controller. `install.sh` generates the database passwords in `.env`, then:

```bash
docker compose --profile unifi up -d
```

The UI is at `https://<pi-ip>:8443` (self-signed certificate, accept the warning). The Pi 4 CPU cannot run recent MongoDB, so `unifi-db` is pinned to `mongo:4.4.18`; if it logs "Illegal instruction", try `mongo:4.4.9`. The first start creates the `unifi` database user through `unifi/init-mongo.sh`. If you ever need to start the database from scratch, delete `data/unifi-db/` while the containers are stopped.

**Adopting the access point** (the provider router keeps doing DHCP):

1. Factory reset the AP (hold the reset button about 10 seconds).
2. Finish the setup wizard in the controller. Then go to *Settings -> System -> Network Application* and set the **Inform host** to the Pi's IP, with *Override* ticked.
3. The AP appears under *UniFi Devices* as pending. Adopt it. If it never shows up, SSH into the AP (user `ubnt`, password `ubnt` after a reset) and run `set-inform http://<pi-ip>:8080/inform`, then adopt again.
4. Recreate your Wi-Fi network with the same name and password as before, so your devices reconnect without changes.

## Notes

- Mosquitto allows anonymous connections, which is fine on a home LAN but not on an exposed network.
- `data/` holds all state and is git-ignored. Keep `backups/` somewhere off the Pi.

## Licence

Noodle is free software under the [GNU General Public License v3.0 or later](LICENSE): you may use, study, change and share it, and anyone who shares a modified version must share it under the same licence, so it stays open for everyone. Contributions are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md).
