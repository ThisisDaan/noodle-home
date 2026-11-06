"""Integration plugins. Each integration is one folder here (plugin.py, adapter.py, __init__.py exposing PLUGIN)."""

from __future__ import annotations

import functools
import importlib
import pkgutil

from .base import Field, Integration, Node, NodeField, Plugin, PressButton

__all__ = ["Field", "Integration", "Node", "NodeField", "Plugin", "PressButton", "discover", "node_types"]


@functools.cache
def node_types() -> dict[str, tuple[Plugin, Node]]:
    """Every flow node a plugin adds, by type."""
    found: dict[str, tuple[Plugin, Node]] = {}
    for plugin in discover():
        for node in plugin.nodes():
            if node.type in found:
                raise RuntimeError(f"Two plugins add the node {node.type}")
            found[node.type] = (plugin, node)
    return found


@functools.cache
def discover() -> list[Plugin]:
    """Every folder here whose package exposes a `PLUGIN`, in page order."""
    found = []
    for module in pkgutil.iter_modules(__path__):
        if not module.ispkg:
            continue
        plugin = getattr(importlib.import_module(f"{__name__}.{module.name}"), "PLUGIN", None)
        if plugin is not None:
            found.append(plugin)
    ids = [p.id for p in found]
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"Two plugins share an id: {sorted(i for i in ids if ids.count(i) > 1)}")
    return sorted(found, key=lambda p: (p.order, p.id))
