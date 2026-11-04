# Changelog

The Noodle hub follows [semantic versioning](https://semver.org). The version is `__version__` in `noodle/backend/noodle/__init__.py`; a release is a git tag `vX.Y.Z` with the same number (the release workflow checks it).

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
