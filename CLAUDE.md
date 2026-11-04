# Noodle hub (repo notes)

This repo has two things: the Raspberry Pi stack (`compose.yaml`, `install.sh`, `backup.sh`, Mosquitto, Zigbee2MQTT, Home Assistant, Thread) and the Noodle hub in `homepi/` (the product), plus the Android app in `noodle-android/`.

## The hub (`homepi/`)

- Backend: `homepi/backend/homepi/` (FastAPI, Python 3.11+). Frontend: `homepi/frontend/` (SvelteKit, Svelte 5 runes, Bun, Tailwind/daisyUI).
- **Integrations are plugins** in `backend/homepi/plugins/` (one module each, exposing `PLUGIN`). Adding one needs no change elsewhere except its setting keys in `config.SETTINGS`. See the README section "Writing an integration".
- **Config is YAML files** in `<data>/config/`: `flows/*.yaml` (the automations, source of truth), `settings.yaml`, `secrets.yaml`, `dashboard.yaml`, `areas.yaml`. SQLite (`homepi.db`) holds runtime state only (history, timers, login). Writes go through `yamlfile.YamlFile` / `flowfiles.FlowFiles`, which keep comments.
- Flow nodes: built-in ones are described in `nodespec.py` (types and settings) and run in `flows.py`; nodes an integration adds come from `Plugin.nodes()`.
- Do not poll from the frontend: the server pushes changes over `/api/ws`.

## Commands

```bash
cd homepi/backend && pip install -r requirements-dev.txt && pytest     # backend tests
cd homepi/frontend && bun install && bun run check && bun run build   # type check, build
python -m homepi validate                                             # check flow files
./homepi/build-wheel.sh                                                # pip wheel with the interface inside
```

## Rules for changes

- New flows from files or an AI start switched off; keep it that way (`FlowEngine._apply_file`, `/api/flow/import`).
- Anything that migrates a user's data needs a test with the old shape and must be safe to run twice.
- Keep personal device ids, names and addresses out of the code and examples. Use placeholders.
- A live hub runs from this code on a Pi: back up `data/homepi/homepi.db` before deploying, and dry-run migrations on a copy.
- Flow-writing guidance for AIs is in `docs/AI.md`; the prompt text is `RULES` in `homepi/backend/homepi/aicontext.py`.
