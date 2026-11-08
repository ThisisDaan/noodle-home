# Configuration

Everything on this page can be set up in the app. The files are how Noodle stores it, and they are there for power users, backups, version control and AI assistants.

All files live in `<data>/config/` (in Docker: `/data/config/`). The app picks up a hand edit within a couple of seconds and keeps your comments when it saves.

## Flows

Every automation is a YAML file in `config/flows/`. The visual editor writes the same files. A flow that is new to the app (copied in, or written by an AI) always starts switched off.

Example flows (a blanket and a heater with safety cut-offs) are in [`noodle/backend/noodle/examples/flows/`](../noodle/backend/noodle/examples/flows/).

```bash
noodle validate    # check all flow files
noodle schema      # JSON Schema of the format, with the nodes you have installed
```

In Docker: `docker compose exec noodle python -m noodle validate`. `GET /api/flow/schema` serves the same schema, and device ids come from `GET /api/devices`. The format is documented in `noodle/backend/noodle/flowfiles.py`. Letting an AI write flows is described in [AI.md](AI.md).

## Config files

| File | Holds |
|---|---|
| `flows/*.yaml` | your automations, one per file |
| `settings.yaml` | one section per integration (`zigbee:`, `hue:`, ...) and the list of added integrations |
| `secrets.yaml` | keys and tokens such as the Hue key and ntfy topic; readable by the owner only, keep it out of git |
| `dashboard.yaml` | dashboard cards, room order, hidden and pinned devices, tile order, card designs (`cards:`) |
| `areas.yaml` | your rooms, and the name and room you gave each device |
| `hue-hooks.yaml` | only for an older Hue Tap/Dimmer setup forwarded through Home Assistant (see `examples/hue-hooks.yaml`) |

Changing a setting restarts only the integration it belongs to. The database (`noodle.db`) holds runtime state only: history, timers and the login.

## Custom devices

On the Devices page, *New custom device* makes a device of your own with the values it should remember: on/off, a number (with a unit and optional min, max and step) or text. Automations fill them in with the **Write to entity** step, and they behave like any other device: they show on the Devices page, other flows react to them, and they can go on the dashboard.

The older flow variables are the text fields of a built-in *Variables* device (*Set variable* and *Check variable* still work).

## Card designer

Open any device and press *Design the card*. Pick a size, tap a slot, and choose a component and the field it shows.

| Size | Slots |
|---|---|
| Small | 2 |
| Wide (two tiles wide) | 4 |
| Large (two wide, two high) | 12 |

| Component | Slots | For |
|---|---|---|
| Switch | 1 | something that can be on or off |
| Value | 1 | any reading or text |
| Dial (− and +) | 2 | a number, or a thermostat's target |
| Slider | 1 | a number, or a light's brightness |
| Graph | 2 × 2 | the last hours of a number |

A device's default look is built from the same components, so the designer always opens on what the card shows now.

## Environment variables

| Variable | Purpose |
|---|---|
| `NOODLE_DATA` | data folder (database and `config/`) |
| `NOODLE_CONFIG` | config folder, if not `<data>/config` |
| `NOODLE_PORT` | web port (default `8090`) |
| `NOODLE_EXTRA_PORT` | second port, default `80` so `http://noodle.local` works without a port (`0` = off) |
| `NOODLE_URL` | the hub's public address |
| `NOODLE_LAT`, `NOODLE_LON`, `NOODLE_TZ` | location and time zone (also set in the setup wizard) |
| `NOODLE_AUTOMATIONS` | `0` stops flows from running (for development) |
| `MQTT_HOST`, `MATTER_URL`, `OTBR_URL` | point a development hub at services elsewhere |

The older `HOMEPI_*` names still work.
