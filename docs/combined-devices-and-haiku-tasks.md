# Combined devices ("Combine") and a Haiku-ready task list

Two parts: (A) the design for devices made from other devices, (B) the remaining refactor work cut into tasks small
enough for a cheap model. Written 2026-11-06.

## A. Combined devices

### Problem

A heater on a smart plug, a room sensor and a target temperature is one thing to the user, but today it is a flow
(`trigger.thermostat` plus switch nodes, see `examples/flows/safety-heater.yaml`) and three unrelated tiles. Home
Assistant's "helpers" solve this with opaque, separate objects. Noodle can do better: one device, built from a
template, backed by a flow you can read.

### Shape

- A **composite** is a YAML file in `<data>/config/combined/<id>.yaml`, like flows (comments kept, written through
  `yamlfile.YamlFile`, reloaded when edited).
- It appears in the hub as an ordinary device (new adapter source `combined`, new plugin folder
  `plugins/combined/`), with its own tile, room, name and state. Members are listed on the device and stay visible.
- Each template has: the inputs it asks for, the controls it shows (face), and the flow nodes it generates.
- The generated flow is a normal file in `flows/` named `combined-<id>.yaml`, marked `generated_by: combined`.
  The user can open it. Editing the combined file regenerates it; editing the flow by hand detaches it (flag it).
- Rules from CLAUDE.md apply: anything imported from files or an AI starts switched off; no polling (state pushed
  over `/api/ws`); only local devices; no personal ids in examples.

### Templates, in build order

1. **Heater** (first, it is the real use case): inputs `sensor` (device + key), `plug` (device), `target` (default
   20), `margin` (default 0.5), `max_on_minutes` (default 120), `sensor_lost_minutes` (default 15). Controls: on/off,
   target. Safety is part of the template, not optional: plug off when the sensor has been silent too long, and off
   after `max_on_minutes`. Generates the same nodes as `safety-heater.yaml`.
2. **Timer switch**: a plug that turns itself off after N minutes.
3. **Threshold sensor**: a sensor value turned into on/off with a margin (humidity above 70).
4. **Group**: fold the existing `groups` plugin in later; not needed for the first release.

### Template contract (Python, in `plugins/combined/templates/<name>.py`)

```python
class HeaterTemplate(Template):
    id = "heater"
    name = "Heater"
    inputs = [Input("sensor", "device_key"), Input("plug", "device"), Input("target", "number", 20), ...]
    def validate(self, values) -> list[str]: ...      # readable errors, empty = ok
    def flow(self, cid, values) -> dict: ...          # the generated flow file content
    def face(self, values) -> list[Control]: ...      # on/off, target
```

The frontend asks `GET /api/combined/templates` for the inputs and draws one generic form (no per-template
Svelte). "Combine" is a button on the Devices page that opens that dialog.

### Status (2026-11-06)

Built: `plugins/combined/` with three templates (heater, timer switch, threshold sensor), the API under
`/api/combined`, the Combine dialog on the Devices page (and Edit in the device sheet), a thermostat tile face
(`devices/ThermostatFace.svelte`, used for every `climate` device), reload of `config/combined/*.yaml` when edited,
and tests in `tests/test_combined.py`. Tried in a browser against a dev hub with two fake devices (create, turn on,
tile updates live, flow enabled). Not tried with real devices. A missing member makes the combined device show as
offline; its flow is not switched off (devices load at different times at start-up).

### Open questions (decide before building)

- Does the combined device's on/off mean "thermostat enabled" (recommended) or "plug on"? Show plug state as a
  read-only value either way.
- Deleting a combined device: delete its generated flow too (recommended), never the members.
- A member removed from the hub: mark the combined device "needs attention", and switch its flow off.

### Tests to write

Old/new shape is not an issue (new feature), but: template validate errors; generated flow passes
`python -m noodle validate`; generated flow starts switched off when it comes from an import; removing the combined
device removes its flow and not the members; saving twice produces identical flow files.

## B. Haiku-ready tasks

Rule for every task: change only the listed files, run `cd noodle/backend && pytest`, and stop with the failing
output if anything fails. Do not touch anything else. Each task ships alone.

| # | Task | Files | Done when |
|---|---|---|---|
| H1 | Move the mDNS browsing code in `lan/adapter.py`, `dirigera/adapter.py`, `homeassistant/plugin.py` onto `noodle/mdns.py` (extend it with a function that takes service types and a callback; Hue already uses it) | those 3 + `mdns.py` | pytest passes; the three files no longer import `zeroconf` directly |
| H2 | Add `udp_probe(payload, port, seconds, parse)` to a new `noodle/udp.py` and switch kasa, wiz, roku, yeelight, govee `search` to it, one plugin per commit | `udp.py`, 5 adapters | pytest passes; each adapter's search is under 15 lines |
| H3 | Naming: make folder, id and source agree (`mqttdisc`/`mqtt`, `hub_settings`/`system`, `groups`/`group`). Rename folders only, keep ids and saved settings unchanged | 3 folders, imports, tests | pytest passes; no saved-config key changes |
| H4 | Add the remaining contract test: `details()` keys do not collide with core device keys | `tests/test_plugins.py` | test added and passing |
| H5 | Remove `custom_form` (no plugin sets it): `base.py`, `integrations.py`, frontend types and `IntegrationForm.svelte` | those | pytest and `bun run check` pass |
| H6 | Add a new LAN integration by copying `plugins/wled/` (give the device name when you want one) | new folder + `config.SETTINGS` | pytest passes |

Keep for a stronger model (do not give to Haiku): plan steps 4 (flag consolidation, API shape change), 5, 6, 7 and
part A (design decisions, new adapter, flow generation).

Suggested way to run it: one subagent per row with `model: "haiku"`, the row copied into its prompt together with
the rule above, then review each diff before committing.
