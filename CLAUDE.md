# Noodle hub (repo notes)

This repo has two things: the Raspberry Pi stack (`compose.yaml`, `install.sh`, `backup.sh`, Mosquitto, Zigbee2MQTT, Home Assistant, Thread) and the Noodle hub in `noodle/` (the product), plus the Android app in `noodle-android/`.

## The hub (`noodle/`)

- Backend: `noodle/backend/noodle/` (FastAPI, Python 3.11+). Frontend: `noodle/frontend/` (SvelteKit, Svelte 5 runes, Bun, Tailwind/daisyUI).
- **Integrations are plugins** in `backend/noodle/plugins/` (one module each, exposing `PLUGIN`). Adding one needs no change elsewhere except its setting keys in `config.SETTINGS`. See the README section "Writing an integration".
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

- New flows from files or an AI start switched off; keep it that way (`FlowEngine._apply_file`, `/api/flow/import`).
- Anything that migrates a user's data needs a test with the old shape and must be safe to run twice.
- Keep personal device ids, names and addresses out of the code and examples. Use placeholders.
- Only support devices and services that can be controlled locally (LAN, local API, Zigbee, Matter, BLE). No cloud-only integrations; a cloud account may be needed once to pair, never to run.
- Never scan for devices in a background loop. Discovery runs only while the user starts a search (`discovery.py`, `Discover.svelte`); added devices are saved and polled by address.
- A live hub runs from this code on a Pi: back up `data/noodle/noodle.db` before deploying, and dry-run migrations on a copy.
- Flow-writing guidance for AIs is in `docs/AI.md`; the prompt text is `RULES` in `noodle/backend/noodle/aicontext.py`.
