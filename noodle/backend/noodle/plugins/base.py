"""What an integration plugin looks like. A plugin is one module in this package with a module-level
`PLUGIN`: it says what the integration is called, which settings it has and how to build its adapter.
The Integrations page and the start-up code are generated from the plugins, so adding an integration
means adding a module here and nothing else."""

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
    custom_form: bool = False


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
    id: str = ""
    name: str = ""
    help: str = ""
    fields: list[Field] = []
    gated: bool = False  # the adapter only runs while the integration is added
    always: bool = False  # not something to add or remove
    visible: bool = True  # False: runs, but has no entry on the Integrations page
    icon: str = "plug"  # name of an icon in the interface (frontend/src/lib/Icon.svelte)
    panel: str | None = None  # a component of the Integrations page shown with the settings (see lib/integrations/panels.ts)
    custom_form: bool = False  # the panel replaces the settings form and the help text
    forget: list[str] = []  # config keys cleared when the integration is removed
    order: int = 100  # position on the page; lower comes first
    adapter_class: type | None = None
    source: str | None = None  # the adapter's `source`; None when there is no adapter
    searchable: bool = False  # the page has a Search button; see search() and add_found(), and discovery.py
    noun: str = "devices"  # what a search looks for, for the interface: "bulbs", "sensors", ...
    search_hint: str = ""  # shown while searching: what to do on the device (put it in pairing mode, ...)
    press_hint: str = ""  # shown while waiting for the button, when add_found raises PressButton
    restart_after_add: bool = False  # add_found changed settings, so the adapter reconnects

    def create_adapter(self, hub) -> Any:
        """The adapter that talks to the service (None if the plugin only has settings)."""
        return self.adapter_class(hub) if self.adapter_class else None

    def status(self, adapter) -> bool | None:
        """True connected, False not, None unknown."""
        return None

    def preset(self) -> bool:
        """Counts as added before the user ever used the Integrations page, because it is already set up."""
        return False

    def details(self, adapter) -> dict:
        """More to show on the page next to the settings."""
        return {}

    async def search(self, adapter, seconds: float, found) -> None:
        """Look for new devices for `seconds`, only when the user asked. Call found(key, name=..., detail=...)
        for each one. Nothing should look for devices outside of this."""
        raise NotImplementedError

    async def add_found(self, adapter, key: str) -> None:
        """The user added one of the things search() found. Raise PressButton if the device first needs a button
        pressed; raise KeyError or ValueError with a message the user can read if it cannot be added. Things that
        join by themselves (Zigbee) are reported as found(..., added=True) and need no add_found."""
        raise NotImplementedError

    def on_remove(self, hub, adapter) -> None:
        """Called when the user removes the integration, after its `forget` keys are cleared."""

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
                           custom_form=self.custom_form)
