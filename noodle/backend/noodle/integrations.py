"""Which integrations the user added, and how the Integrations page shows one. What each integration is
(its settings, status and endpoints) lives in its plugin, see plugins/."""

from __future__ import annotations

from . import config, plugins
from .plugins import Integration


def added_ids() -> list[str]:
    """What the user added. Before they ever used the page, whatever was already set up counts as added."""
    if config.INTEGRATIONS:
        return config.INTEGRATIONS
    if not config.SETUP_DONE:  # a new hub: the user picks in the first-run wizard
        return []
    return [p.id for p in plugins.discover() if p.visible and not p.always and p.preset()]


def describe(item: Integration, plugin=None, adapter=None) -> dict:
    return {
        "id": item.id, "name": item.name, "help": item.help, "connected": item.status(), "icon": item.icon, "panel": item.panel,
        "custom_form": item.custom_form,
        **({"noun": plugin.noun, "search_hint": plugin.search_hint, "press_hint": plugin.press_hint}
           if plugin and plugin.searchable else {}),
        **(plugin.details(adapter) if plugin else {}),
        "added": item.always or item.id in added_ids(), "always": item.always,
        "fields": [{"key": f.key, "label": f.label, "placeholder": f.placeholder, "secret": f.secret, "hidden": f.hidden, "help": f.help, "advanced": f.advanced,
                    "value": "" if f.secret else config.get_text(f.key),
                    "set": bool(config.get_text(f.key)) if f.secret else None} for f in item.fields],
    }
