# Changelog

The Noodle hub follows [semantic versioning](https://semver.org). The version is `__version__` in `noodle/backend/noodle/__init__.py`; a release is a git tag `vX.Y.Z` with the same number (the release workflow checks it).

## 0.2.0

- **Set up new Shellies.** Shelly's Search also lists Shellies that are not on the Wi-Fi yet (new or reset). Pick the home Wi-Fi (hidden networks too), enter the password and press Connect: the hub hands the Shelly the Wi-Fi details and adds it once it shows up. Works on Linux (NetworkManager) and Windows; the password is never stored. New devices come first in the search results, and each row shows its progress, the outcome or why it failed. See `docs/integrations.md` for what the hub needs.
- **Zigbee setup** in the first-run wizard: it finds and checks the MQTT broker Zigbee2MQTT uses. Search screens start searching when they open (Zigbee pairing still waits for the button).
- Setup screens keep their buttons and errors in view while the content scrolls. Fixed the hidden Wi-Fi password and "Add by IP address" fields, and "Search failed: NotImplementedError" for Shelly on Windows.
- **Themes.** System › Appearance has a theme picker for the whole hub: Noodle (Noodle Light or Noodle Dark, following each device, as before), or Noodle Light, Noodle Dark, Dracula, Nord, Night, Dim, Sunset, Synthwave, Forest, Coffee, Emerald, Cupcake, Winter or Corporate (daisyUI's themes). Every open page and the app change at once; the choice is kept in `settings.yaml` (`appearance: theme: dracula`).
- **Backups.** System › Backups downloads one file with everything (flows, settings, rooms, dashboard, history) and restores one with a preview of what changes. The hub also makes a backup every night at 03:00 and keeps the last 7, plus one before every restore, in `<data>/backups/`. A restore is applied on the next start, before anything opens the files, and the hub restarts itself (no Docker or systemd needed).
- **Old things removed.** The "Set variable", "Check variable" and "Wait" steps are gone (use *Write to entity*, *Check state*, which can now also check that text *does not equal* a value, and *Timer*). The upgrades that rewrote flows from before the current formats, the old Thermostat integration settings, the `homepi.db` file name and the `HOMEPI_*` environment variables are no longer read. A hub that still has flows or settings in those old formats has to be upgraded with an earlier version first. The Hue switch bridge (`homepi/hook` and `hue-hooks.yaml`) is unchanged.

## 0.1.3

- **A face for each kind of device.** Temperature/humidity sensors show both values large, lights get a brightness slider on their tile, buttons show the last press and can be pressed from the device sheet (a test press runs automations like a real one), motion sensors show motion or clear and since when. One `DeviceFace` component chooses, on tiles and in the sheet.
- ntfy notifications retry once and a timeout now says what failed instead of showing an empty error. The integration is named "Ntfy".

## 0.1.2

- **One way to add devices.** Every integration that can find devices (Philips Hue, Zigbee2MQTT, Bluetooth, LIFX) has the same Search screen: a button that looks for 30 seconds, only when pressed. Hue shows the same "press the button" step as any tap-to-pair device. "Zigbee (Zigbee2MQTT)" is now just "Zigbee2MQTT".

## 0.1.1

First published release: the Docker image and the in-app update check. Same features as 0.1.0 (never released).

## 0.1.0

First version that can be installed on its own. Licensed under GPL-3.0-or-later.

- **Integrations are plugins.** Zigbee (Zigbee2MQTT), Matter and Thread, Philips Hue, Bluetooth sensors, ntfy notifications, Docker containers. Each one is a module in `plugins/` with its settings, status, endpoints, flow nodes and System page info; the Integrations page is generated from them.
- **Automations are YAML files** in `config/flows/`, editable by hand, by an AI or in the visual editor (comments are kept). New flows always start switched off. `noodle validate` and `noodle schema` check them.
- **AI authoring.** "Ask an AI / import" copies a prompt with your real devices, validates the answer and adds it switched off. API: `/api/flow/context`, `/api/flow/import`, `/api/flow/validate`, `/api/flow/schema`.
- **Settings are YAML too:** `settings.yaml`, `secrets.yaml` (owner only), `dashboard.yaml`, `areas.yaml`. Hand edits are picked up within seconds; only the integration a setting belongs to reconnects.
- **First-run wizard** for new hubs: name, location and time zone, services, connecting them, a first device.
- **Dashboard cards** (status, favourites, rooms, quick actions, sensor graph) and device list grouping and sorting.
- **Updates:** *Check for updates* on the System page compares with the latest GitHub release; *Update* pulls the new image and restarts Noodle into it.
- **Packaging:** `pip install` of a wheel with the interface inside (`noodle` command), a hub-only `noodle/compose.yaml`, and a systemd unit template.
- Docker is optional: without a socket the System page simply has no containers section.

**Renamed:** the project is Noodle everywhere now. The `homepi/` folder is `noodle/`, the Python package is `noodle` (the pip package is `noodle-home`), the container and compose service are `noodle`, the data folder is `data/noodle/`, and the database is `noodle.db`. Nothing breaks for existing setups: the older `HOMEPI_*` environment variables, an existing `homepi.db`, the `homepi.webui` container label and the `homepi/hook/<name>` MQTT topic keep working. If you run the full Pi stack, move your data once before `docker compose up`: `mv data/homepi data/noodle`, and remove the old container with `docker compose up -d --remove-orphans`.

Upgrading from the earlier Docker-only version: data is migrated on first start (settings, flows, rooms and device names move into `config/`; nothing is deleted). Forwarded Hue Tap/Dimmer buttons from an older Home Assistant setup now need `config/hue-hooks.yaml` (see `examples/hue-hooks.yaml`).
