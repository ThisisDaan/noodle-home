# Letting an AI write your automations

Every automation (a *flow*) is a small YAML file, so an AI can write one for you. The hub gives the AI everything it needs, and nothing it writes runs until you have looked at it and switched it on.

## In the app

1. Open **Automations**, press **Ask an AI / import**.
2. **Copy prompt.** It contains the file format, every node you can use, your real devices with their ids and entities, your rooms, your existing flows and two examples.
3. Paste it into an AI chat and describe what you want at the end ("turn the hallway light on when the door opens after sunset, off after 5 minutes").
4. Paste the answer into the box. The hub checks it as you paste: errors say what is wrong, warnings say when it names a device that is not on this hub.
5. **Add (switched off)**, read it in the editor, then switch it on.

A flow whose id already exists is only replaced if you say so, and the replacement is switched off too.

## Connect an AI directly (MCP)

The hub is an MCP server at `http://<hub>:<port>/mcp`. Once connected, the AI reads your devices, writes the flow, checks it and adds it (switched off) on its own, with no copy and paste. It can read the hub and add flows; it cannot control devices.

Easiest: in **Automations → Connect an AI**, pick your tool (Claude Code, Claude Desktop, Cursor, VS Code, Codex, Gemini CLI or other) and copy what it shows. Every tool gets its own key, and **Disconnect** in the same window removes it. Or by hand:

1. Get a token (once; the password is not stored anywhere):

```bash
curl -X POST http://noodle.local:8080/api/auth/app -H "Content-Type: application/json" -d '{"password":"YOUR PASSWORD","name":"Claude"}'
```

2. Add the server to your AI tool:

```bash
claude mcp add --transport http noodle http://noodle.local:8080/mcp --header "Authorization: Bearer YOUR_TOKEN"
```

Other tools that take a JSON config (Cursor, VS Code, Claude Desktop through `mcp-remote`) need the same URL and an `Authorization: Bearer YOUR_TOKEN` header. Tools: `get_context`, `list_devices`, `list_flows`, `validate_flow`, `import_flow`.

## From the command line or an AI coding tool

Flows live in `<data>/config/flows/*.yaml` (in Docker: `data/noodle/config/flows/`). The hub reloads a file within a couple of seconds.

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

## Cards

A flow can also describe a card for the dashboard (controls such as a switch or a dial, and readings to show). The AI context explains the format, so you can ask for "a heater with a target dial on the dashboard". See the Cards section of the README.

## Rules the hub enforces

- A flow that is new to the hub always starts **switched off**, whatever its file says.
- A file with errors is not loaded; the previous version of that flow keeps running and the problem shows on the Automations page.
- Warnings (unknown device, unknown setting) do not stop a flow from loading. Read them.

## Tips for good prompts

- Say which devices by name; the AI sees their ids in the prompt.
- Say what should happen when something goes wrong (a sensor goes silent, the plug draws too much power).
- Ask for a comment above each step so you can review it quickly.
