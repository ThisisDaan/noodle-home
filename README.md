# pi4_docker

Mosquitto, Zigbee2MQTT and Home Assistant as plain Docker containers on a Raspberry Pi 4.

## Run just the Noodle hub

Noodle (the `homepi/` folder) does not need the rest of this repository. It talks to the services you already have (a Zigbee2MQTT broker, a Matter server, a Hue bridge, Bluetooth sensors) and you add only the ones you use in the setup wizard.

**With Docker** (Linux; it needs the host network to find devices):

```bash
cd homepi
docker compose up -d --build
```

Open `http://<this machine>:8090`. Your data and settings are in `homepi/data/` (flows are plain files in `data/config/flows/`).

**With pip** (Python 3.11 or newer):

```bash
./homepi/build-wheel.sh                 # builds the interface and a wheel (needs bun and `pip install build`)
python3 -m venv /opt/noodle/venv
/opt/noodle/venv/bin/pip install homepi/backend/dist/noodle_hub-*.whl
HOMEPI_DATA=$HOME/noodle-data /opt/noodle/venv/bin/noodle
```

To keep it running, copy `homepi/noodle.service` to `/etc/systemd/system/`, edit the user and paths in it and run `sudo systemctl enable --now noodle`. Bluetooth sensors need BlueZ on the machine. `noodle --help` lists the other commands (`noodle validate`, `noodle schema`).

Everything below is the full Raspberry Pi stack this project started as: Mosquitto, Zigbee2MQTT, Home Assistant, Thread and Noodle as Docker containers.

## Setup

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. Set hostname, user, password and SSH under *Edit settings*.
2. Plug in the Zigbee stick, boot the Pi and give it a fixed IP in your router.
3. Copy this folder to the Pi and run the installer:

   ```bash
   scp -r pi4_docker youruser@homepi.local:~/
   ssh youruser@homepi.local
   cd pi4_docker && chmod +x install.sh backup.sh && ./install.sh
   ```

| Service | URL |
|---|---|
| Home Assistant | `http://<pi-ip>:8123` |
| Zigbee2MQTT | `http://<pi-ip>:8081` |
| MQTT broker | `<pi-ip>:1883` |

## Restoring your old setup

The `backups/` folder (git-ignored) holds the old setup. Its files already match this compose file, so they can be dropped in as they are. Do this on the Pi after `install.sh` has run once:

```bash
docker compose down
cp -a backups/z2m-backup.*/{configuration.yaml,database.db,coordinator_backup.json} data/zigbee2mqtt/
sudo cp -a backups/automatic_backup_2025_12_3/homeassistant/data/. data/homeassistant/
docker compose up -d
```

- **Zigbee2MQTT:** the old config already uses `mqtt://mosquitto:1883`, port 8080 and the zstack adapter. Compose maps your stick to `/dev/ttyUSB0`, which is what that config expects.
- **Home Assistant:** the backup is an unprotected, extracted `/config` folder, so no restore wizard or encryption key is needed. Its MQTT integration points at `192.168.1.104:1883`, so **give the Pi that same IP** (fixed IP in your router) and it connects with no changes.
- `install.sh` sets `ZIGBEE_DEVICE` in `.env` to your stick's stable path from `ls /dev/serial/by-id/`. If you have several USB devices, set it by hand.

After the first login a short setup wizard asks for your home's name and location, which services you use, and helps pair a first device. Every step can be skipped, and hubs that were set up before the wizard existed never see it.

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
5. In Home Assistant, add these integrations under *Settings -> Devices & services*:
   - **Open Thread Border Router** with URL `http://127.0.0.1:8082`
   - **Thread** (usually discovered automatically). Mark the OTBR network as preferred and use *Send credentials to phone* so the Companion app can pair devices.
   - **Matter** with URL `ws://127.0.0.1:5580/ws`
6. Pair Thread/Matter devices with the Home Assistant Companion app (*Add device -> Add Matter device*). Your phone needs Bluetooth on and has to be on the same Wi-Fi.

## homepi

`homepi/` is our own hub: a FastAPI backend (`homepi/backend`) with a SvelteKit + Tailwind + daisyUI interface (`homepi/frontend`, built with Bun). It runs at `http://noodle.local` (needs the Pi's hostname set to `noodle`: `sudo hostnamectl set-hostname noodle`) or `http://<pi-ip>:8090`; the first visit asks you to choose a password.

- **Zigbee** through Zigbee2MQTT over MQTT: device list, state, switching and dimming, and opening Zigbee pairing for 60 seconds.
- **Matter** straight from `matter-server`: devices, switching and dimming, and button events with their real press counts.
- **Thread** status from `otbr`, and **containers** (status, restart, logs) through the Docker socket.
- Device names and rooms are stored in `data/homepi/homepi.db`.

Develop locally against the Pi: run the backend with `MQTT_HOST=<pi-ip> MATTER_URL=ws://<pi-ip>:5580/ws OTBR_URL=http://<pi-ip>:8082 HOMEPI_DATA=./dev-data python -m homepi` from `homepi/backend`, and `bun run dev` in `homepi/frontend` (it proxies `/api` to port 8090).

`matter2mqtt` forwards Matter button events to MQTT (`matter/<node>/<endpoint>/<event>`) for Home Assistant's scroll wheel automation.

## Optional: UniFi controller

Your U6 Pro needs a controller. `install.sh` generates the database passwords in `.env`, then:

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

## Flows as files

Every automation is a YAML file in `data/homepi/config/flows/` (inside the container: `/data/config/flows/`). Edit them by hand or with an AI; the app reloads a changed file within a couple of seconds, and the visual editor writes the same files (your comments are kept). A flow that is new to the app always starts switched off.

Example flows (a blanket and a heater with safety cut-offs) are in `homepi/backend/homepi/examples/flows/`: copy one into that folder and change the device ids to yours.

```bash
docker compose exec homepi python -m homepi validate    # check all flow files
docker compose exec homepi python -m homepi schema      # JSON Schema of the format, with the nodes you have installed
```

`GET /api/flow/schema` serves the same schema; device ids for `device_id` come from `GET /api/devices`. Format and an example: `homepi/backend/homepi/flowfiles.py`.

## Other config files

Next to `flows/` in `data/homepi/config/`, all YAML, all editable by hand (the app picks up an edit within a couple of seconds and keeps your comments when it saves):

| File | Holds |
|---|---|
| `settings.yaml` | one section per integration (`zigbee:`, `hue:`, ...) and the list of added integrations |
| `secrets.yaml` | Hue key and ntfy topic, readable by the owner only (keep it out of git) |
| `dashboard.yaml` | rooms order, hidden and pinned devices, tile order |
| `areas.yaml` | your rooms, and the name and room you gave each device |

Changing a setting restarts just the integration it belongs to. Clearing a device name by hand needs a restart to show the original name again. An older `settings.json` is moved over on first start (kept as `settings.json.migrated`).

## Writing an integration

Each integration is one module in `homepi/backend/homepi/plugins/` with a module-level `PLUGIN`. Nothing else has to change: the Integrations page, start-up, settings files, flow editor and System page are built from the plugins.

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

Optional hooks: `preset()` (already set up counts as added), `routes()` (own API endpoints), `details()` and `panel` (extra panel on the page, a component listed in `frontend/src/lib/integrations/panels.ts`), `system_info()` (shown on the System page), `forget` and `on_remove()` (cleanup when removed). Add the setting keys to `SETTINGS` in `config.py` with the plugin id as section. The tests in `homepi/backend/tests` check that the pieces agree (`pip install -r requirements-dev.txt`, then `pytest`).
