"""What each kind of entity is and can do. Adapters translate their devices into these kinds; flows, the API and
the interface only know the kinds, never the brand or protocol.

An entity has a `kind`, a `state`, and optional `attrs` (extra readings such as colour or cover position).
Controllable kinds take commands. `on`, `brightness` and `toggle` are the basic ones every adapter understands;
the others below are "extra" commands that an adapter lists in its `extra_commands` when it can do them.

  kind           state                         attrs                                    extra commands
  light          bool                          can, color_temp, color_temp_range, color color_temp (kelvin), color {h, s}
  switch         bool
  fan            bool                          mode, modes                              mode
  cover          "open" | "closed"             position (0-100, 100 = open)             action (open, close, stop), position
  lock           "locked" | "unlocked"                                                  action (lock, unlock)
  climate        target temperature (number)   current, mode, modes, min, max, step     value (target), mode
  number         a settable value                                                       value
  sensor, binary_sensor, button: read only (see hub.py)

`attrs["can"]` on a light lists the extra commands it supports (e.g. ["color_temp", "color"]).
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field

COVER_ACTIONS = ("open", "close", "stop")
LOCK_ACTIONS = ("lock", "unlock")


@dataclass(frozen=True)
class Kind:
    controllable: bool = False
    extra: frozenset[str] = field(default_factory=frozenset)  # commands beyond on / brightness / toggle


KINDS: dict[str, Kind] = {
    "light": Kind(True, frozenset({"color_temp", "color"})),
    "switch": Kind(True),
    "fan": Kind(True, frozenset({"mode"})),
    "cover": Kind(True, frozenset({"action", "position"})),
    "lock": Kind(True, frozenset({"action"})),
    "climate": Kind(True, frozenset({"value", "mode"})),
    "number": Kind(True, frozenset({"value"})),
    "sensor": Kind(),
    "binary_sensor": Kind(),
    "button": Kind(),
}

CONTROLLABLE = frozenset(k for k, v in KINDS.items() if v.controllable)


def clean_extra(kind: str, extra: dict) -> dict:
    """Check the extra commands for an entity kind and return them with their values in range.
    Raises ValueError for a command the kind does not have or a value that does not make sense."""
    given = {k: v for k, v in extra.items() if v is not None}
    spec = KINDS.get(kind)
    if spec is None or not spec.controllable:
        raise ValueError(f"{kind} cannot be controlled")
    for name in given:
        if name not in spec.extra:
            raise ValueError(f"{kind} does not take '{name}'")
    if "action" in given:
        allowed = COVER_ACTIONS if kind == "cover" else LOCK_ACTIONS
        if given["action"] not in allowed:
            raise ValueError(f"action must be one of {', '.join(allowed)}")
    if "position" in given:
        given["position"] = _number(given["position"], "position", 0, 100)
    if "color_temp" in given:
        given["color_temp"] = int(_number(given["color_temp"], "color_temp", 1000, 10000))
    if "color" in given:
        color = given["color"]
        if not isinstance(color, dict) or "h" not in color or "s" not in color:
            raise ValueError("color needs h (0-360) and s (0-100)")
        given["color"] = {"h": _number(color["h"], "h", 0, 360), "s": _number(color["s"], "s", 0, 100)}
    if "value" in given:
        given["value"] = _number(given["value"], "value", -1000, 1000)
    if "mode" in given:
        given["mode"] = str(given["mode"])
    return given


def _number(value, name: str, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return number


def xy_to_hs(x: float, y: float) -> dict:
    """CIE xy colour (as lights report it) to hue 0-360 and saturation 0-100."""
    if y <= 0:
        return {"h": 0.0, "s": 0.0}
    X, Z = x / y, (1 - x - y) / y
    r, g, b = 3.2406 * X - 1.5372 - 0.4986 * Z, -0.9689 * X + 1.8758 + 0.0415 * Z, 0.0557 * X - 0.2040 + 1.0570 * Z
    r, g, b = (max(0.0, c) for c in (r, g, b))
    top = max(r, g, b) or 1.0
    h, s, _ = colorsys.rgb_to_hsv(r / top, g / top, b / top)
    return {"h": round(h * 360, 1), "s": round(s * 100, 1)}
