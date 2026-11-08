"""Which integrations the user added, and how the Integrations page shows one. What each integration is
(its settings, status and endpoints) lives in its plugin, see plugins/."""

from __future__ import annotations

import logging

from . import config, plugins
from .plugins import Integration

log = logging.getLogger(__name__)


def added_ids() -> list[str]:
    """What the user added. Before they ever used the page, whatever was already set up counts as added."""
    if config.INTEGRATIONS:
        return config.INTEGRATIONS
    if not config.SETUP_DONE:  # a new hub: the user picks in the first-run wizard
        return []
    return [p.id for p in plugins.discover() if p.visible and not p.always and p.preset()]


def _status(item: Integration) -> bool | None:
    try:
        return item.status()
    except Exception as err:  # an integration that cannot say how it is doing shows as unknown
        log.warning("%s: status failed: %s", item.id, err)
        return None


def _details(plugin, adapter) -> dict:
    """What the plugin adds to its entry. One that fails must not break the whole page."""
    if plugin is None:
        return {}
    try:
        return plugin.details(adapter)
    except Exception as err:
        log.warning("%s: details failed: %s", plugin.id, err)
        return {"error": f"{err.__class__.__name__}: {err}"}


def describe(item: Integration, plugin=None, adapter=None) -> dict:
    return {
        "id": item.id, "name": item.name, "help": item.help, "connected": _status(item), "icon": item.icon, "panel": item.panel,
        "support": item.support, "search_finds": plugin.search_finds if plugin else "devices",
        "can_add": bool(plugin and plugin.search_finds == "devices" and (plugin.searchable or plugin.manual_add)), "add_text": plugin.add_text if plugin else "",
        **({"noun": plugin.noun, "search_hint": plugin.search_hint, "press_hint": plugin.press_hint}
           if plugin and plugin.searchable else {}),
        **_details(plugin, adapter),
        "added": item.always or item.id in added_ids(), "always": item.always,
        "fields": [{"key": f.key, "label": f.label, "placeholder": f.placeholder, "secret": f.secret, "hidden": f.hidden, "help": f.help, "advanced": f.advanced,
                    "value": "" if f.secret else config.get_text(f.key),
                    "set": bool(config.get_text(f.key)) if f.secret else None} for f in item.fields],
    }
