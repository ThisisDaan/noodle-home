"""MCP server: lets an AI assistant (Claude, ChatGPT, Cursor, ...) work with this hub.

Served by the hub itself at POST /mcp (MCP "streamable HTTP", stateless, JSON replies), signed in with the same
app token as the phone app. No extra process and no extra dependency. See docs/AI.md for how to connect.

The tools only read the hub and add flows that start switched off; they cannot control devices.
"""

import json

from fastapi import APIRouter, Depends, Request, Response

PROTOCOL = "2025-03-26"
SERVER = {"name": "noodle", "version": "1"}

YAML_ARG = {"type": "object", "properties": {"yaml": {"type": "string", "description": "The text of one flow file."}},
            "required": ["yaml"]}

TOOLS = [
    {"name": "get_context",
     "description": "START HERE before writing a flow. Returns the flow file format, every node type, the devices "
                    "(ids, entities, current state), rooms, existing flows and examples, as markdown.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_devices",
     "description": "The devices on this hub with their entities and current state.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_flows",
     "description": "The existing automations: id, name, and whether each is switched on.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "validate_flow",
     "description": "Check a flow file without saving it. Returns ok, errors and warnings (such as unknown "
                    "devices). Fix every error before importing.",
     "inputSchema": YAML_ARG},
    {"name": "import_flow",
     "description": "Add a flow from the text of a flow file. It always starts switched off; tell the user to "
                    "review it in Noodle and switch it on. An existing id is only replaced when replace is true.",
     "inputSchema": {"type": "object", "required": ["yaml"],
                     "properties": {**YAML_ARG["properties"], "replace": {"type": "boolean"}}}},
]


def _text(value, error: bool = False) -> dict:
    text = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
    return {"content": [{"type": "text", "text": text}], "isError": error}


def router(require_login, *, context, devices, flows, validate, import_flow) -> APIRouter:
    """`require_login` is the hub's login check; the rest are functions that give the tools their data."""
    api = APIRouter()
    handlers = {
        "get_context": lambda a: _text(context()),
        "list_devices": lambda a: _text(devices()),
        "list_flows": lambda a: _text(flows()),
        "validate_flow": lambda a: _text(validate(str(a.get("yaml", ""))), False),
        "import_flow": lambda a: _text(import_flow(str(a.get("yaml", "")), bool(a.get("replace", False)))),
    }

    def call(name: str, args: dict) -> dict:
        handler = handlers.get(name)
        if not handler:
            return _text(f"Unknown tool: {name}", True)
        try:
            result = handler(args if isinstance(args, dict) else {})
        except Exception as e:  # a tool failure goes back to the AI, which can react to it
            return _text(f"{type(e).__name__}: {e}", True)
        if name in ("validate_flow", "import_flow"):
            parsed = json.loads(result["content"][0]["text"])
            result["isError"] = not parsed.get("ok", False)
        return result

    def reply(msg: dict) -> dict | None:
        method, id_ = msg.get("method"), msg.get("id")
        if id_ is None:  # a notification (e.g. notifications/initialized) gets no answer
            return None
        if method == "initialize":
            result = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": SERVER,
                      "instructions": "Call get_context first, write the flow file, validate_flow until ok, then "
                                      "import_flow. Imported flows are switched off until the user turns them on."}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = msg.get("params") or {}
            result = call(params.get("name", ""), params.get("arguments") or {})
        else:
            return {"jsonrpc": "2.0", "id": id_, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": id_, "result": result}

    @api.post("/mcp", dependencies=[Depends(require_login)], include_in_schema=False)
    async def mcp(request: Request) -> Response:
        try:
            body = await request.json()
        except ValueError:
            return Response(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}),
                            media_type="application/json", status_code=400)
        batch = body if isinstance(body, list) else [body]
        out = [r for m in batch if isinstance(m, dict) and (r := reply(m)) is not None]
        if not out:
            return Response(status_code=202)
        return Response(json.dumps(out if isinstance(body, list) else out[0]), media_type="application/json")

    @api.get("/mcp", dependencies=[Depends(require_login)], include_in_schema=False)
    def mcp_stream() -> Response:
        return Response(status_code=405, headers={"Allow": "POST"})  # no server-initiated stream

    return api
