# Plugin architecture: review and refactor plan

Written after a read-only review of how integrations ("plugins") are built and whether that fits the rest of the app.
The review was done by an Opus model on 2026-11-05; the findings below were checked against the code by reading it,
not by running real hardware.

## Verdict

One folder per integration (`plugins/<name>/{plugin.py,adapter.py,__init__.py}`), automatic discovery, the shared
search screen and the `LanAdapter`/`LanPlugin` base are the right design. The contract around it grew by adding
flags rather than by design: about 20 overlapping `Plugin` attributes, a description dict built in three layers, a
core that still names specific integrations, and a README claim ("only touches its own folder") that is not true.
It needs consolidating before more integrations are added.

## Done (shipped, with tests)

- Panel forms no longer bubble a submit into the settings form (it saved settings and restarted the adapter, which
  could cut off a Matter pairing). `IntegrationForm.svelte` saves only for its own submit.
- Removing an integration removes its devices by default (`Plugin.on_remove`); Zigbee and Matter were leaving them.
- Nanoleaf: found devices that were already added are not offered again; a missed button press is a `PressButton`
  wait, and the device stays in the found list.
- A failing `details()`, `status()` or `system_info()` no longer breaks the Integrations or System page.
- Saving settings does not start an integration that is not added.
- Govee asks the light for its model after a restart.
- Rules ("never scan in the background", local only): LIFX no longer broadcasts on its own to find a moved bulb;
  Bluetooth only records what is nearby while a Search runs; Hue search uses the bridge's own mDNS announcement
  (`noodle/mdns.py`) instead of Philips' cloud lookup.

## Still open

Small: none (`forget` and `/api/notify` are now documented in the code).

Design, in order (each step ships on its own with the tests passing):

1. **Contract tests over every plugin** (done for panels, search, describe and `config_attr`; the hard-coded id/order lists remain) instead of the hard-coded id/order/adapter lists in `tests/test_plugins.py`.
   Add: `describe()` is JSON-serialisable and `details()` keys do not collide with core keys; every `panel` exists in
   `panels.ts`; every `searchable` plugin overrides `search`; `LanPlugin.config_attr` equals its adapter's `attr`.
2. **(Done: `status`, `search`, `add_found` and the device loop in `on_remove` now have defaults; the Lan, Lifx, Ble, Dirigera, Zigbee, Pi-hole, UniFi and Home Assistant copies are gone.) Defaults in `Plugin`** for `status`, `search` and `add_found` when the adapter has the method; delete the copies
   (the connected/error `status()` is repeated 4 times, `search`/`add_found` delegation 5 times, and several plugins
   still copy the `on_remove` loop).
3. **(Done: lan, dirigera and homeassistant use `mdns.browse`; kasa, wiz, roku, yeelight and govee use `udp.udp_probe`.) Shared search helpers.** `noodle/mdns.py` exists (used by Hue). Move the mDNS copies in `lan/adapter.py`,
   `dirigera/adapter.py` and `homeassistant/plugin.py` onto it, and add a `udp_probe(...)` helper for the five
   copies in kasa, wiz, roku, yeelight and govee.
4. **Fewer flags.** (Done: `single` and `adds_devices` are now `search_finds: "devices" | "connection" | "hub"`, and `custom_form` is removed.) Still open: nest `details()` under a `details` key; fold the lifecycle flags (`gated`,
   `always`, `visible`, `preset`) into something readable; `order` is an int.
5. **Settings owned by the plugin.** Let a plugin declare its settings (key, kind, default, secret) so `config.py`
   builds `SETTINGS`, `SECRET_KEYS` and the module globals from the plugins. Remove `config_attr`, `setting` and
   `attr`. Then a new integration needs no edit outside its folder (apart from a panel, if it wants one).
6. **Data-described panels.** A plugin returns a small description (status line, list with Remove, input with
   button, message) that one shared Svelte component draws. It would cover Lan, Lifx, Ble, Hue, Dirigera, Zigbee and
   Notify; Matter (QR scan) and Location (map) stay custom components. This also lets integrations be added without
   rebuilding the frontend.
7. **Core stops naming plugins.** `main.py` unpacks five adapters by name and wires `zigbee.on_hook` to `hue.press`;
   groups, phone and notify routes live in `main.py`; the frontend limits `source` to six values and capitalises ids
   instead of using plugin names. Send the plugin name with devices.
8. **(Folder names now match ids; docs wording done.) Naming and order.** Folder and id disagree in three places (`mqttdisc`/`mqtt`, `hub_settings`/`system`,
   `groups`/`group`); `base.py` and `CLAUDE.md` still say "one module"; group the `Plugin` attributes (lifecycle, UI,
   search); fix the README claim that a new integration only touches its folder (today it also needs `config.py`
   globals and `SETTINGS`, the hard-coded test lists, and `panels.ts`).
9. **Third-party plugins** (entry-point discovery, plugin-supplied settings) once steps 5 and 6 are done.

## Rules to keep in mind (from CLAUDE.md)

Only local control; never scan in a background loop (discovery runs only while the user has pressed Search); anything
that migrates user data needs a test with the old shape and must be safe to run twice; back up
`data/noodle/noodle.db` before deploying; keep personal device ids and addresses out of the code and examples.
