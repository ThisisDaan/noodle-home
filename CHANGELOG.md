# Changelog

The Noodle hub follows [semantic versioning](https://semver.org). The version is `__version__` in `homepi/backend/homepi/__init__.py`; a release is a git tag `vX.Y.Z` with the same number (the release workflow checks it).

## 0.1.0

First version that can be installed on its own.

- **Integrations are plugins.** Zigbee (Zigbee2MQTT), Matter and Thread, Philips Hue, Bluetooth sensors, ntfy notifications, a thermostat, Docker containers. Each one is a module in `plugins/` with its settings, status, endpoints, flow nodes and System page info; the Integrations page is generated from them.
- **Automations are YAML files** in `config/flows/`, editable by hand, by an AI or in the visual editor (comments are kept). New flows always start switched off. `noodle validate` and `noodle schema` check them.
- **AI authoring.** "Ask an AI / import" copies a prompt with your real devices, validates the answer and adds it switched off. API: `/api/flow/context`, `/api/flow/import`, `/api/flow/validate`, `/api/flow/schema`.
- **Settings are YAML too:** `settings.yaml`, `secrets.yaml` (owner only), `dashboard.yaml`, `areas.yaml`. Hand edits are picked up within seconds; only the integration a setting belongs to reconnects.
- **First-run wizard** for new hubs: name, location and time zone, services, connecting them, a first device.
- **Dashboard cards** (status, favourites, rooms, quick actions, sensor graph) and device list grouping and sorting.
- **Packaging:** `pip install` of a wheel with the interface inside (`noodle` command), a hub-only `homepi/compose.yaml`, and a systemd unit template.
- Docker is optional: without a socket the System page simply has no containers section.

Upgrading from the earlier Docker-only version: data is migrated on first start (settings, flows, rooms and device names move into `config/`; nothing is deleted). Forwarded Hue Tap/Dimmer buttons from an older Home Assistant setup now need `config/hue-hooks.yaml` (see `examples/hue-hooks.yaml`).
