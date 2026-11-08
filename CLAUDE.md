# Noodle hub (repo notes)

This repo is only Noodle: the hub in `noodle/` (the product) and the Android app in `noodle-android/`. The author's own Raspberry Pi stack (Mosquitto, Zigbee2MQTT, Home Assistant, Thread, UniFi) lives outside this repo in `../home-network`; do not add it back.

## The hub (`noodle/`)

- Backend: `noodle/backend/noodle/` (FastAPI, Python 3.11+). Frontend: `noodle/frontend/` (SvelteKit, Svelte 5 runes, Bun, Tailwind/daisyUI).
- **Integrations are plugins** in `backend/noodle/plugins/<name>/` (one folder each: `plugin.py` says what it is, `adapter.py` how it talks to the device, `__init__.py` exposes `PLUGIN`). Adding one needs no change elsewhere except its setting keys in `config.SETTINGS`. See `docs/integrations.md`.
- **Config is YAML files** in `<data>/config/`: `flows/*.yaml` (the automations, source of truth), `settings.yaml`, `secrets.yaml`, `dashboard.yaml`, `areas.yaml`. SQLite (`noodle.db`, or `homepi.db` on hubs that already had it) holds runtime state only (history, timers, login). Writes go through `yamlfile.YamlFile` / `flowfiles.FlowFiles`, which keep comments.
- Flow nodes: built-in ones are described in `nodespec.py` (types and settings) and run in `flows.py`; nodes an integration adds come from `Plugin.nodes()`.
- Do not poll from the frontend: the server pushes changes over `/api/ws`.

## Commands

```bash
cd noodle/backend && pip install -r requirements-dev.txt && pytest     # backend tests
cd noodle/frontend && bun install && bun run check && bun run build   # type check, build
python -m noodle validate                                             # check flow files
./noodle/build-wheel.sh                                                # pip wheel with the interface inside
```

## Rules for changes

- **A user never has to touch a YAML file.** The files are how things are stored and what an AI or a power user may write, but every feature (flows, settings, areas, dashboard) must be fully usable and editable in the app, with pickers and dropdowns instead of typed ids. A feature that can only be set up in YAML is not finished. Ask the user how a new feature should feel to use before building it.
- New flows from files or an AI start switched off; keep it that way (`FlowEngine._apply_file`, `/api/flow/import`).
- Anything that migrates a user's data needs a test with the old shape and must be safe to run twice.
- Keep personal device ids, names and addresses out of the code and examples. Use placeholders.
- Only support devices and services that can be controlled locally (LAN, local API, Zigbee, Matter, BLE). No cloud-only integrations; a cloud account may be needed once to pair, never to run.
- Never scan for devices in a background loop. Discovery runs only while the user starts a search (`discovery.py`, `Discover.svelte`); added devices are saved and polled by address.
- A live hub runs from this code on a Pi: back up `data/noodle/noodle.db` before deploying, and dry-run migrations on a copy.
- Flow-writing guidance for AIs is in `docs/AI.md`; the prompt text is `RULES` in `noodle/backend/noodle/aicontext.py`.
