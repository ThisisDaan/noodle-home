# Letting an AI write your automations

Every automation (a *flow*) is a small YAML file, so an AI can write one for you. The hub gives the AI everything it needs, and nothing it writes runs until you have looked at it and switched it on.

## In the app

1. Open **Automations**, press **Ask an AI / import**.
2. **Copy prompt.** It contains the file format, every node you can use, your real devices with their ids and entities, your rooms, your existing flows and two examples.
3. Paste it into an AI chat and describe what you want at the end ("turn the hallway light on when the door opens after sunset, off after 5 minutes").
4. Paste the answer into the box. The hub checks it as you paste: errors say what is wrong, warnings say when it names a device that is not on this hub.
5. **Add (switched off)**, read it in the editor, then switch it on.

A flow whose id already exists is only replaced if you say so, and the replacement is switched off too.

## From the command line or an AI coding tool

Flows live in `<data>/config/flows/*.yaml` (in Docker: `data/homepi/config/flows/`). The hub reloads a file within a couple of seconds.

```bash
noodle schema                 # JSON Schema of the format (with the integrations you have installed)
noodle validate               # check every flow file; exits 1 on errors
noodle validate my-flow.yaml  # check one file
```

The same information as the prompt is available from the API (log in first):

| Endpoint | What |
|---|---|
| `GET /api/flow/context` | JSON: instructions, format, nodes, devices, rooms, flows, examples |
| `GET /api/flow/context?format=markdown` | the same as one prompt to paste |
| `GET /api/flow/schema` | JSON Schema |
| `POST /api/flow/validate` `{yaml}` | check text without saving |
| `POST /api/flow/import` `{yaml, replace?}` | add a flow, switched off |

## Rules the hub enforces

- A flow that is new to the hub always starts **switched off**, whatever its file says.
- A file with errors is not loaded; the previous version of that flow keeps running and the problem shows on the Automations page.
- Warnings (unknown device, unknown setting) do not stop a flow from loading. Read them.

## Tips for good prompts

- Say which devices by name; the AI sees their ids in the prompt.
- Say what should happen when something goes wrong (a sensor goes silent, the plug draws too much power).
- Ask for a comment above each step so you can review it quickly.
