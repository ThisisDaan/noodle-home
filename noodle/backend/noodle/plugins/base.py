"""What an integration plugin looks like. A plugin is one folder in this package (`plugin.py`, `adapter.py`, `__init__.py`)
exposing a module-level `PLUGIN`: it says what the integration is called, which settings it has and how to build
its adapter. The Integrations page and the start-up code are generated from the plugins. Adding an integration
means adding a folder here, plus its setting keys in `config.SETTINGS` (and a panel in `panels.ts` if it wants one)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .. import config


class PressButton(Exception):
    """Raised by `add_found` when the device waits for a button press (Philips Hue, ...). The page then shows
    the same "press the button" screen for every integration and asks again until the button was pressed."""


@dataclass
class Field:
    key: str  # a key of config.SETTINGS
    label: str
    placeholder: str = ""
    secret: bool = False  # never sent back to the browser
    hidden: bool = False  # not in the settings form: the integration's panel sets it (the map sets the location)
    help: str = ""  # a sentence under the input
    advanced: bool = False  # tucked under "Advanced", after the integration's panel


@dataclass
class Integration:
    """One entry of the Integrations page."""
    id: str
    name: str
    help: str
    fields: list[Field]
    adapter: str | None = None  # adapter that reconnects when the settings change
    gated: bool = False  # the adapter only runs while the integration is added
    always: bool = False  # not something to add or remove (the hub's own settings)
    status: Callable[[], bool | None] = lambda: None  # True connected, False not, None unknown
    icon: str = "plug"
    panel: str | None = None
    support: str = "untested"  # "supported" or "untested", see Plugin.support


@dataclass
class NodeField:
    """One input in the node's properties panel. type: text, textarea, number, select or buttons."""
    key: str
    label: str
    type: str = "text"
    options: list[tuple[str, str]] = field(default_factory=list)  # select: (value, label)
    hint: str = ""


@dataclass
class Node:
    """A flow node an integration adds. `run` gets a flows.NodeRun: .data, .msg, .store, .hub, .fill(text),
    .log(text) and .follow(handle="out"), which sends the message on to the next nodes."""
    type: str  # "action.<name>", "trigger.<name>" or "cond.<name>"
    label: str
    category: str  # trigger, condition or action
    run: Callable[[Any], Any]
    defaults: dict = field(default_factory=dict)
    fields: list[NodeField] = field(default_factory=list)
    icon: str = "circle"
    summary: str = ""  # one line shown in the node, with {key} filled from its settings

    def describe(self) -> dict:
        return {"type": self.type, "label": self.label, "category": self.category, "defaults": self.defaults,
                "icon": self.icon, "summary": self.summary,
                "fields": [{"key": f.key, "label": f.label, "type": f.type, "hint": f.hint,
                            "options": [list(o) for o in f.options]} for f in self.fields]}


class Plugin:
    # --- Identity
    id: str = ""
    name: str = ""
    help: str = ""
    fields: list[Field] = []
    # --- Lifecycle: when it runs, whether it can be added or removed
    gated: bool = False  # the adapter only runs while the integration is added
    always: bool = False  # not something to add or remove
    visible: bool = True  # False: runs, but has no entry on the Integrations page
    # "supported": the maintainers run it on real devices. "untested": written from the device's protocol but not yet
    # confirmed on real hardware (the Integrations page says so). New integrations start as untested.
    support: str = "untested"
    # --- What the Integrations page shows
    icon: str = "plug"  # name of an icon in the interface (frontend/src/lib/Icon.svelte)
    panel: str | None = None  # a component of the Integrations page shown with the settings (see lib/integrations/panels.ts)
    # Config keys cleared when the integration is removed. Also, when settings are edited in the files,
    # `main._apply_settings` uses these (with `fields`) to decide which plugin a changed key belongs to.
    forget: list[str] = []
    # --- Adapter
    order: int = 100  # position on the page; lower comes first
    adapter_class: type | None = None
    source: str | None = None  # the adapter's `source`; None when there is no adapter
    # --- Search and adding devices (see discovery.py)
    searchable: bool = False  # the page has a Search button; see search() and add_found(), and discovery.py
    manual_add: bool = False  # devices are added without a search (a setup code): the panel has the form, shown in the Add device dialog
    add_text: str = ""  # one line for the Add device list when there is no search, e.g. "Pair with a setup code"
    # What Search/pairing adds: "devices" (lights, sensors...), "connection" (one of several, like a Hue bridge: its
    # devices join by themselves) or "hub" (exactly one connection, like a DIRIGERA hub; set up once).
    search_finds: str = "devices"
    noun: str = "devices"  # what a search looks for, for the interface: "bulbs", "sensors", ...
    search_hint: str = ""  # shown while searching: what to do on the device (put it in pairing mode, ...)
    press_hint: str = ""  # shown while waiting for the button, when add_found raises PressButton
    restart_after_add: bool = False  # add_found changed settings, so the adapter reconnects

    def create_adapter(self, hub) -> Any:
        """The adapter that talks to the service (None if the plugin only has settings)."""
        return self.adapter_class(hub) if self.adapter_class else None

    def status(self, adapter) -> bool | None:
        """True connected, False not, None unknown. By default read from the adapter's `connected` and `error`."""
        if getattr(adapter, "connected", None):
            return True
        return False if getattr(adapter, "error", None) else None

    def preset(self) -> bool:
        """Counts as added before the user ever used the Integrations page, because it is already set up."""
        return False

    def details(self, adapter) -> dict:
        """More to show on the page next to the settings."""
        return {}

    async def search(self, adapter, seconds: float, found) -> None:
        """Look for new devices for `seconds`, only when the user asked. Call found(key, name=..., detail=...)
        for each one. Nothing should look for devices outside of this. By default the adapter's own `search`."""
        if not hasattr(adapter, "search"):
            raise NotImplementedError
        await adapter.search(seconds, found)

    async def add_found(self, adapter, key: str) -> None:
        """The user added one of the things search() found. Raise PressButton if the device first needs a button
        pressed; raise KeyError or ValueError with a message the user can read if it cannot be added. Things that
        join by themselves (Zigbee) are reported as found(..., added=True) and need no add_found.
        By default the adapter's own `add_found`."""
        if not hasattr(adapter, "add_found"):
            raise NotImplementedError
        await adapter.add_found(key)

    def on_remove(self, hub, adapter) -> None:
        """Called when the user removes the integration, after its `forget` keys are cleared. By default its devices
        leave the hub; a plugin overrides this to clean up more."""
        if self.source:
            for device_id in [d.id for d in hub.devices.values() if d.source == self.source]:
                hub.remove(device_id)

    def system_info(self, adapter) -> dict | None:
        """What the System page shows about this integration (None: nothing). May be a coroutine function."""
        return None

    def nodes(self) -> list[Node]:
        """Flow nodes this integration adds."""
        return []

    def routes(self, adapter, ctx):
        """A FastAPI APIRouter with this integration's own endpoints, or None."""
        return None

    def describe(self, adapter) -> Integration:
        return Integration(self.id, self.name, self.help, list(self.fields), adapter=self.source, gated=self.gated,
                           always=self.always, status=lambda: self.status(adapter), icon=self.icon, panel=self.panel,
                           support=self.support)
