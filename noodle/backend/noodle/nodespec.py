"""What the built-in flow nodes are and which settings each takes. Used to check flow files and to write their
JSON Schema, so people and AI know exactly what a flow may contain. Nodes that integrations add describe
themselves (see plugins/base.py Node); the engine in flows.py documents what each built-in node does.

Field types: str, num, int, bool, list, any. A field is (type, description) or (type, description, [allowed values])."""

from __future__ import annotations

DEVICE = {"device_id": ("str", "Device id, e.g. zigbee:0x00158d0001a2b3c4 or matter:4 (see GET /api/devices)"),
          "key": ("str", "Entity key on that device, e.g. switch, brightness, temperature")}
DEVICE_ACTIONS = ["on", "off", "toggle", "brightness", "brighter", "dimmer", "loop_start", "loop_stop", "message",
                  "open", "close", "stop", "lock", "unlock"]

CORE: dict[str, dict] = {
    "trigger.state": {
        "label": "Device changes", "category": "trigger",
        "help": "Fires when an entity of a device changes. One output per ticked change, named '<entity>:on', "
                "'<entity>:off' (or '<entity>:out' for a number).",
        "fields": {**DEVICE, "outputs": ("list", "Ticked changes, e.g. ['occupancy:on', 'occupancy:off']")}},
    "trigger.event": {
        "label": "Button pressed", "category": "trigger",
        "help": "Fires on a button press. One output per ticked '<button>:<press>' (press: single, double, long_press...).",
        "fields": {"device_id": DEVICE["device_id"], "outputs": ("list", "Ticked presses, e.g. ['action:single']"),
                   "keys": ("list", "Older flows: the buttons this node listens to"),
                   "action": ("str", "Older flows: the press this node listens to")}},
    "trigger.thermostat": {
        "label": "Thermostat", "category": "trigger",
        "help": "Outputs 'cold' (at or below target - margin) and 'warm' (at or above target + margin), once per crossing. "
                "Input 'check' re-reads the temperature now.",
        "fields": {**DEVICE, "target": ("num", "Target temperature in °C"), "margin": ("num", "Degrees either side of the target")}},
    "trigger.time": {
        "label": "Time of day", "category": "trigger", "help": "Fires every day (or on the given weekdays) at a time.",
        "fields": {"at": ("str", "Time as HH:MM"), "days": ("list", "Weekdays, Monday = 0; empty = every day")}},
    "trigger.interval": {
        "label": "Every...", "category": "trigger", "help": "Fires every N seconds.",
        "fields": {"seconds": ("num", "Seconds between runs")}},
    "trigger.webhook": {
        "label": "Phone notification button", "category": "trigger",
        "help": "Fires when a button with this name is tapped on a phone notification.",
        "fields": {"name": ("str", "Button name, as set in the Notify node")}},
    "trigger.sun": {
        "label": "Sunrise / sunset", "category": "trigger", "help": "Fires at sunrise or sunset.",
        "fields": {"event": ("str", "sunrise or sunset", ["sunrise", "sunset"]),
                   "offset": ("num", "Minutes after (negative = before)")}},
    "trigger.manual": {"label": "Run button", "category": "trigger",
                       "help": "Fires when the flow is run by hand or by 'Run another flow'.", "fields": {}},
    "cond.state": {
        "label": "Check state", "category": "condition",
        "help": "On/off entities have outputs 'on' and 'off'. With op (numbers) the outputs are 'yes' and 'no'.",
        "fields": {**DEVICE, "op": ("str", "Comparison for numbers", ["", "eq", "gt", "lt"]),
                   "value": ("any", "Value to compare with")}},
    "cond.for": {
        "label": "In state for...", "category": "condition",
        "help": "Yes when an entity has been on/off (or above/below a value) for at least N minutes. Survives restarts.",
        "fields": {**DEVICE, "state": ("str", "on, off, above or below", ["on", "off", "above", "below"]),
                   "minutes": ("num", "How long"), "value": ("any", "Limit for above/below")}},
    "cond.time": {"label": "Between times", "category": "condition", "help": "Yes when now is between two times.",
                  "fields": {"from": ("str", "HH:MM"), "to": ("str", "HH:MM")}},
    "cond.var": {"label": "Check variable", "category": "condition", "help": "Yes when a variable equals / differs.",
                 "fields": {"name": ("str", "Variable name"), "op": ("str", "eq or neq", ["eq", "neq"]),
                            "value": ("any", "Value to compare with")}},
    "cond.day": {"label": "Day of the week", "category": "condition", "help": "Yes when today is one of the days.",
                 "fields": {"days": ("list", "Weekdays, Monday = 0")}},
    "cond.dark": {"label": "Is it dark?", "category": "condition", "help": "Yes between sunset and sunrise.", "fields": {}},
    "action.device": {
        "label": "Control device", "category": "action",
        "help": "One input per ticked action. 'message' applies msg.payload {brightness|on|toggle} to the device.",
        "fields": {**DEVICE, "command": ("str", "Older flows: the single action", DEVICE_ACTIONS),
                   "inputs": ("list", f"Ticked actions, from: {', '.join(DEVICE_ACTIONS)}"),
                   "brightness": ("num", "Percent for 'brightness'"), "step": ("num", "Percent per press for brighter/dimmer"),
                   "min": ("num", "Lowest brightness for dimmer"), "loop_levels": ("list", "Brightness loop levels, 0 = off"),
                   "loop_seconds": ("num", "Seconds per loop step"), "loop_max_seconds": ("num", "Stop the loop after")}},
    "action.cycle": {
        "label": "Cycle", "category": "action",
        "help": "Sends the next of a list of messages. Inputs: next, back (stop at the ends), loop (wraps).",
        "fields": {"inputs": ("list", "Which of next / back / loop to show"), "steps": ("list", "Messages, e.g. [{brightness: 25}]")}},
    "action.repeat": {"label": "Repeat", "category": "action",
                      "help": "Inputs start/stop: sends the message every N seconds until stopped.",
                      "fields": {"seconds": ("num", "Seconds between messages"), "max_seconds": ("num", "Stop after")}},
    "action.delay": {"label": "Wait", "category": "action", "help": "Waits, then continues.",
                     "fields": {"seconds": ("num", "Seconds")}},
    "action.timer": {"label": "Timer", "category": "action",
                     "help": "Countdown with inputs 'start' and 'stop'; continues when it runs out.",
                     "fields": {"minutes": ("num", "Minutes"), "restart": ("bool", "A new start begins again (true) or is ignored (false)")}},
    "action.log": {"label": "Log message", "category": "action", "help": "Writes a line to the flow log.",
                   "fields": {"message": ("str", "Text; {count}, {temperature} and {now} are filled in")}},
    "action.var": {"label": "Set variable", "category": "action", "help": "Sets a variable.",
                   "fields": {"name": ("str", "Variable name"), "value": ("str", "Value; {now} is filled in")}},
    "action.throttle": {"label": "Only once per...", "category": "action",
                        "help": "Lets a message through at most once per N minutes.",
                        "fields": {"minutes": ("num", "Minutes")}},
    "action.http": {"label": "Call web address", "category": "action", "help": "Calls a URL. A failure is logged, not fatal.",
                    "fields": {"url": ("str", "Address"), "method": ("str", "HTTP method, e.g. GET or POST"),
                               "body": ("str", "Request body")}},
    "action.flow": {"label": "Run another flow", "category": "action",
                    "help": "Runs the 'Run button' triggers of another flow.", "fields": {"flow_id": ("str", "Id of that flow")}},
}
