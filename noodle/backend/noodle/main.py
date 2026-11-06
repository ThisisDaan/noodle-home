"""FastAPI app: REST API, live WebSocket and the built SvelteKit interface."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import types
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import aicontext, config, flowfiles, integrations, mcp, notify, plugins, updates
from .plugins import PressButton
from .flows import FlowEngine
from .discovery import Discovery
from .migrations import adopt_hue_buttons, retire_thermostat
from .hub import Hub
from .store import Store
from .yamlfile import YamlFile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("noodle")

store = Store(config.db_path())
hub = Hub(store)
PLUGINS = plugins.discover()
ADAPTERS = {p.source: p.create_adapter(hub) for p in PLUGINS if p.source}  # by source, e.g. "zigbee"
zigbee, matter, hue, phone, groups = (ADAPTERS[s] for s in ("zigbee", "matter", "hue", "phone", "group"))
for adapter in ADAPTERS.values():
    hub.register(adapter)
flows = FlowEngine(hub, store)
for adapter in ADAPTERS.values():
    if hasattr(adapter, "attach_flows"):  # adapters that write flows
        adapter.attach_flows(flows)
discovery = Discovery(hub)
adopt_hue_buttons(flows)
retire_thermostat(flows)
# Forwarded presses: Hue switch buttons, or else a phone notification button.
zigbee.on_hook = lambda name: hue.press(name) or flows.webhook(name)

# Notifications also go to the Noodle apps that hold a connection open (see /api/ws).
_app_clients = 0
notify.publish = hub.broadcast
notify.app_clients = lambda: _app_clients

# Failed logins per client address, to slow down guessing.
_failed: dict[str, list[float]] = {}


tasks: dict[str, asyncio.Task] = {}


async def restart_adapter(source: str) -> None:
    """Reconnect one adapter, so it picks up changed settings."""
    if old := tasks.pop(source, None):
        old.cancel()
        await asyncio.gather(old, return_exceptions=True)
    tasks[source] = asyncio.create_task(ADAPTERS[source].run())


async def _apply_settings(changed: set[str]) -> None:
    """Settings were edited in the files: reconnect the integrations they belong to."""
    log.info("settings changed in the files: %s", ", ".join(sorted(changed)))
    added = set(integrations.added_ids())
    for plugin in PLUGINS:
        if not plugin.source:
            continue
        running = plugin.source in tasks and not tasks[plugin.source].done()
        want = not plugin.gated or plugin.id in added
        # `forget` doubles as the list of keys that belong to this plugin besides its fields
        touched = any(k in changed for k in [*(f.key for f in plugin.fields), *plugin.forget])
        if want and (touched or (plugin.gated and not running)):
            await restart_adapter(plugin.source)
        elif not want and running:
            tasks.pop(plugin.source).cancel()


async def _check_config() -> None:
    store.flush()
    if config.files_changed() and (changed := config.load()):
        await _apply_settings(changed)
    if store.reload_areas():
        hub.reapply_meta()
        hub.broadcast({"type": "areas", "areas": store.areas()})
    if dashboard.changed():
        hub.broadcast({"type": "layout", "layout": _read_layout()})


async def watch_config() -> None:
    """Pick up hand edits of the files in config/ (and write what was held back)."""
    while True:
        await asyncio.sleep(2)
        try:
            await _check_config()
        except Exception:
            log.exception("checking the config files failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    hub.loop = asyncio.get_running_loop()
    gated = {i.adapter for i in _integrations() if i.gated and i.id not in integrations.added_ids()}
    for source, adapter in ADAPTERS.items():
        if source not in gated:
            tasks[source] = asyncio.create_task(adapter.run())
    if config.AUTOMATIONS:
        flows.start()
    else:
        log.warning("NOODLE_AUTOMATIONS=0: flows will not run")
    watcher = asyncio.create_task(watch_config())
    yield
    watcher.cancel()
    store.flush()
    flows.stop()
    for task in tasks.values():
        task.cancel()


app = FastAPI(title="Noodle", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=store.session_secret(), session_cookie="noodle",
                   max_age=60 * 60 * 24 * 30, same_site="strict")


def _bearer(headers, query=None) -> str:
    auth = headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else (query or {}).get("token", "")


def require_login(request: Request) -> None:
    if request.session.get("user"):
        return
    token = _bearer(request.headers)
    if token and store.check_app_token(token):
        return
    raise HTTPException(401, "Not logged in")


# --- auth ---------------------------------------------------------------

class PasswordBody(BaseModel):
    password: str = Field(min_length=8)


def _mark_existing_install_done() -> None:
    """A hub that already had a password before the first-run wizard existed does not need the wizard."""
    if store.has_password() and store.get("setup_started") is None and not config.SETUP_DONE:
        config.save({"setup_done": "true"})


_mark_existing_install_done()


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict:
    logged_in = bool(request.session.get("user"))
    return {"setup_needed": not store.has_password(), "logged_in": logged_in,
            "wizard": logged_in and not config.SETUP_DONE}


@app.post("/api/setup/finish", dependencies=[Depends(require_login)])
def finish_setup() -> dict:
    """The first-run wizard was finished or skipped."""
    # Keep what was picked: an empty list would mean "whatever is already set up" (see integrations.added_ids).
    config.save({"setup_done": "true", "integrations": ",".join(integrations.added_ids()) or "none"})
    return {"ok": True}


@app.post("/api/auth/setup")
def auth_setup(body: PasswordBody, request: Request) -> dict:
    if store.has_password():
        raise HTTPException(409, "Password already set")
    store.set_password(body.password)
    store.set("setup_started", "1")  # a new hub: show the first-run wizard
    request.session["user"] = "admin"
    return {"ok": True}


@app.post("/api/auth/login")
def auth_login(body: PasswordBody, request: Request) -> dict:
    client = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _failed.get(client, []) if now - t < 300]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many attempts, wait 5 minutes")
    if not store.check_password(body.password):
        _failed[client] = recent + [now]
        raise HTTPException(401, "Wrong password")
    _failed.pop(client, None)
    request.session["user"] = "admin"
    return {"ok": True}


class AppLoginBody(BaseModel):
    password: str = Field(min_length=8)
    name: str = Field("Android", max_length=40)


@app.post("/api/auth/app")
def auth_app(body: AppLoginBody, request: Request) -> dict:
    """The Noodle app trades the password once for a long-lived token, so the password is never stored on the phone."""
    client = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _failed.get(client, []) if now - t < 300]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many attempts, wait 5 minutes")
    if not store.check_password(body.password):
        _failed[client] = recent + [now]
        raise HTTPException(401, "Wrong password")
    _failed.pop(client, None)
    return {"token": store.add_app_token(body.name)}


class AiConnectionBody(BaseModel):
    name: str = Field("AI assistant", min_length=1, max_length=40)


@app.get("/api/ai/connections", dependencies=[Depends(require_login)])
def ai_connections() -> list[dict]:
    """The AI tools that have been given access to /mcp."""
    return store.app_tokens("ai")


@app.post("/api/ai/connections", dependencies=[Depends(require_login)])
def ai_connect(body: AiConnectionBody) -> dict:
    """Give one AI tool its own token (shown once), made from a logged-in session so the password is not asked again."""
    return {"token": store.add_app_token(body.name, "ai"), "connections": store.app_tokens("ai")}


@app.delete("/api/ai/connections/{token_id}", dependencies=[Depends(require_login)])
def ai_disconnect(token_id: str) -> dict:
    if not store.remove_app_token(token_id, "ai"):
        raise HTTPException(404, "No such connection")
    return {"connections": store.app_tokens("ai")}


@app.get("/api/auth/session", include_in_schema=False)
def auth_session(request: Request) -> RedirectResponse:
    """The Noodle app opens the web interface with its token here; this turns it into a normal login cookie."""
    token = _bearer(request.headers)
    if not token or not store.check_app_token(token):
        raise HTTPException(401, "Not logged in")
    request.session["user"] = "admin"
    return RedirectResponse("/", status_code=303)


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


# --- devices ------------------------------------------------------------

class CommandBody(BaseModel):
    on: bool | None = None
    brightness: int | None = Field(default=None, ge=0, le=100)
    toggle: bool = False
    value: float | None = None
    # Kind-specific commands (capabilities.py)
    color_temp: int | None = None  # kelvin
    color: dict | None = None  # {"h": 0-360, "s": 0-100}
    position: float | None = None  # covers, 0-100
    action: str | None = None  # covers: open, close, stop. locks: lock, unlock
    mode: str | None = None  # fans and thermostats


class MetaBody(BaseModel):
    name: str | None = None
    area: str | None = None
    presence_minutes: float | None = Field(None, ge=0.5, le=24 * 60)


@app.get("/api/devices", dependencies=[Depends(require_login)])
def list_devices() -> list[dict]:
    return [d.as_dict() for d in hub.devices.values()]


@app.post("/api/devices/{device_id}/entities/{key}", dependencies=[Depends(require_login)])
async def command(device_id: str, key: str, body: CommandBody) -> dict:
    if device_id not in hub.devices or key not in hub.devices[device_id].entities:
        raise HTTPException(404, "Unknown device or entity")
    try:
        await hub.command(device_id, key, on=body.on, brightness=body.brightness, toggle=body.toggle, value=body.value,
                          color_temp=body.color_temp, color=body.color, position=body.position, action=body.action,
                          mode=body.mode)
    except (RuntimeError, ValueError) as err:
        raise HTTPException(400, str(err))
    return {"ok": True}


class PressBody(BaseModel):
    action: str = Field(min_length=1, max_length=60)


@app.post("/api/devices/{device_id}/entities/{key}/press", dependencies=[Depends(require_login)])
def press_button(device_id: str, key: str, body: PressBody) -> dict:
    """Act as if the button was pressed (the Devices page's test button): it shows as the last press, is
    recorded in the history and runs the automations that listen to it. The device itself is not involved."""
    device = hub.devices.get(device_id)
    entity = device.entities.get(key) if device else None
    if entity is None or entity.kind != "button":
        raise HTTPException(404, "Unknown button")
    if entity.actions and body.action not in entity.actions:
        raise HTTPException(400, f"This button has no press called {body.action}")
    entity.state = body.action
    hub.changed(device)
    hub.event(device, key, body.action, {"simulated": True})
    return {"ok": True}


@app.put("/api/devices/{device_id}", dependencies=[Depends(require_login)])
def update_device(device_id: str, body: MetaBody) -> dict:
    if device_id not in hub.devices:
        raise HTTPException(404, "Unknown device")
    if body.area and body.area not in store.areas():
        raise HTTPException(400, "Unknown area")
    return hub.set_meta(device_id, body.name, body.area, body.presence_minutes).as_dict()


@app.get("/api/devices/{device_id}/history", dependencies=[Depends(require_login)])
async def device_history(device_id: str, limit: int = 200, since: float = 0) -> list[dict]:
    # async on purpose: it then runs on the event loop with the writers, instead of a thread sharing their sqlite connection
    return store.history(device_id, min(max(limit, 1), 5000), since)


class HistoryBody(BaseModel):
    days: int = Field(ge=-1, le=36500)  # 0 = forever, -1 = off


@app.get("/api/settings/history", dependencies=[Depends(require_login)])
def history_setting() -> dict:
    return {"days": store.history_days()}


@app.put("/api/settings/history", dependencies=[Depends(require_login)])
def set_history_setting(body: HistoryBody) -> dict:
    store.set_history_days(body.days)
    return {"days": body.days}


class PresenceBody(BaseModel):
    minutes: float = Field(ge=0.5, le=24 * 60)


@app.put("/api/devices/{device_id}/presence", dependencies=[Depends(require_login)])
def update_presence(device_id: str, body: PresenceBody) -> dict:
    if device_id not in hub.devices:
        raise HTTPException(404, "Unknown device")
    try:
        return hub.set_presence_minutes(device_id, body.minutes).as_dict()
    except ValueError as err:
        raise HTTPException(400, str(err))


# --- light groups -------------------------------------------------------

class GroupMember(BaseModel):
    device_id: str
    key: str


class GroupBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    members: list[GroupMember] = Field(min_length=1, max_length=50)


def _check_members(body: GroupBody) -> list[dict]:
    for m in body.members:
        device = hub.devices.get(m.device_id)
        entity = device.entities.get(m.key) if device else None
        if not entity or entity.kind != "light" or device.source == "group":
            raise HTTPException(400, f"{m.device_id} is not a lamp")
    return [m.model_dump() for m in body.members]


@app.get("/api/groups", dependencies=[Depends(require_login)])
def list_groups() -> list[dict]:
    return list(groups.groups.values())


@app.post("/api/groups", dependencies=[Depends(require_login)])
def create_group(body: GroupBody) -> dict:
    return groups.save(body.name.strip(), _check_members(body))


@app.put("/api/groups/{group_id}", dependencies=[Depends(require_login)])
def update_group(group_id: str, body: GroupBody) -> dict:
    if group_id not in groups.groups:
        raise HTTPException(404, "Unknown group")
    return groups.save(body.name.strip(), _check_members(body), group_id)


@app.delete("/api/groups/{group_id}", dependencies=[Depends(require_login)])
def delete_group(group_id: str) -> dict:
    groups.delete(group_id)
    return {"ok": True}


# --- areas --------------------------------------------------------------

class AreaBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)


@app.get("/api/areas", dependencies=[Depends(require_login)])
def list_areas() -> list[str]:
    return store.areas()


@app.post("/api/areas", dependencies=[Depends(require_login)])
def add_area(body: AreaBody) -> list[str]:
    store.add_area(body.name.strip())
    return store.areas()


@app.delete("/api/areas/{name}", dependencies=[Depends(require_login)])
def remove_area(name: str) -> list[str]:
    store.remove_area(name)
    for device in hub.devices.values():
        if device.area == name:
            device.area = None
            hub.changed(device)
    return store.areas()


# --- dashboard layout ---------------------------------------------------

# The cards the dashboard can show, in the order of dashboard.yaml. No `widgets` key means the default ones.
WIDGET_TYPES = {"status", "favourites", "rooms", "flows", "sensor"}
DEFAULT_WIDGETS = [{"type": "status"}, {"type": "favourites"}, {"type": "rooms"}]
DEVICE_GROUPS = {"room", "type", "source", "none"}
DEVICE_SORTS = {"name", "recent"}


class LayoutBody(BaseModel):
    rooms: list[str] = Field(default_factory=list, max_length=100)
    hidden: list[str] = Field(default_factory=list, max_length=1000)
    favorites: list[str] = Field(default_factory=list, max_length=1000)
    order: list[str] = Field(default_factory=list, max_length=1000)
    widgets: list[dict] | None = Field(default=None, max_length=50)
    devices_view: dict | None = None


def _clean_widgets(raw) -> list[dict] | None:
    """Keep the widgets that are understood: a known type, with its few settings as plain text or numbers."""
    if not isinstance(raw, list):
        return None
    clean = []
    for item in raw:
        if not isinstance(item, dict) or item.get("type") not in WIDGET_TYPES:
            continue
        widget = {"type": item["type"]}
        for key in ("title", "device_id", "key"):
            if isinstance(item.get(key), str) and item[key]:
                widget[key] = item[key][:100]
        if isinstance(item.get("hours"), (int, float)) and not isinstance(item.get("hours"), bool):
            widget["hours"] = min(max(int(item["hours"]), 1), 24 * 14)
        clean.append(widget)
    return clean


def _clean_devices_view(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {"group_by": raw.get("group_by") if raw.get("group_by") in DEVICE_GROUPS else "room",
            "sort": raw.get("sort") if raw.get("sort") in DEVICE_SORTS else "name"}


# The layout lives in config/dashboard.yaml, where it can be edited by hand.
dashboard = YamlFile(config.CONFIG_DIR / "dashboard.yaml")
if not dashboard.exists() and (_old_layout := store.get("dashboard_layout")):  # before it was a file
    try:
        dashboard.write(LayoutBody.model_validate_json(_old_layout).model_dump())
    except ValueError:
        pass


def _read_layout() -> dict:
    layout = LayoutBody().model_dump()
    try:
        saved = dashboard.read()
    except ValueError as err:
        log.warning("%s (using an empty layout until it is fixed)", err)
        return layout
    for key in ("rooms", "hidden", "favorites", "order"):
        if isinstance(saved.get(key), list):
            layout[key] = [str(item) for item in saved[key]]
    layout["widgets"] = _clean_widgets(saved.get("widgets"))
    layout["devices_view"] = _clean_devices_view(saved.get("devices_view"))
    return layout


@app.get("/api/layout", dependencies=[Depends(require_login)])
def get_layout() -> dict:
    return _read_layout()


@app.put("/api/layout", dependencies=[Depends(require_login)])
def put_layout(body: LayoutBody) -> dict:
    values = body.model_dump(exclude_none=True)
    if body.widgets is not None:
        values["widgets"] = _clean_widgets(body.widgets) or []
    values["devices_view"] = _clean_devices_view(body.devices_view)
    dashboard.write(values)
    return _read_layout()


# --- flows --------------------------------------------------------------

class FlowBody(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    graph: dict | None = None
    enabled: bool | None = None


def _flow(flow_id: str) -> dict:
    if flow_id not in flows.flows:
        raise HTTPException(404, "Unknown flow")
    return flows.flows[flow_id]


@app.get("/api/flow/nodes", dependencies=[Depends(require_login)])
def flow_nodes() -> list[dict]:
    """The nodes integrations add to the flow editor. `available` is false while the integration is not added."""
    added = set(integrations.added_ids())
    return [{**node.describe(), "plugin": plugin.id, "available": not plugin.visible or plugin.always or plugin.id in added}
            for plugin, node in plugins.node_types().values()]


@app.get("/api/flow/schema", dependencies=[Depends(require_login)])
def flow_schema() -> dict:
    """JSON Schema of the flow files, with the nodes of the integrations that are installed."""
    return flowfiles.schema()


@app.get("/api/flow/files", dependencies=[Depends(require_login)])
def flow_files() -> dict:
    """Problems found in the flow files (a file with errors keeps the previous version of its flow running)."""
    return flows.file_issues


class YamlBody(BaseModel):
    yaml: str = Field(max_length=200_000)


@app.post("/api/flow/validate", dependencies=[Depends(require_login)])
def flow_validate(body: YamlBody) -> dict:
    """Check the text of a flow file without saving it: {ok, errors, warnings}, and its id, name and size when ok.
    Warnings include devices the flow names that are not on this hub."""
    return aicontext.check(body.yaml, hub)


class ImportBody(YamlBody):
    replace: bool = False


@app.post("/api/flow/import", dependencies=[Depends(require_login)])
def flow_import(body: ImportBody) -> dict:
    """Add a flow from the text of a flow file. It always starts switched off. A flow with the same id is only
    replaced with replace=true (and then also switched off, so the new version is looked at first).
    Problems come back as {ok: false, errors}, not as an HTTP error."""
    result = aicontext.check(body.yaml, hub)
    if not result["ok"]:
        return result
    flow = flowfiles.from_doc(flowfiles.parse(body.yaml))
    exists = flow["id"] in flows.flows
    if exists and not body.replace:
        return {**result, "ok": False, "exists": True,
                "errors": [f"A flow with the id '{flow['id']}' already exists ({flows.flows[flow['id']]['name']}). "
                           "Change the id, or replace it."]}
    if exists:
        flows.update(flow["id"], flow["name"], flow["graph"], False)
    else:
        flows.create(flow["name"], flow["graph"], enabled=False, flow_id=flow["id"])
    return {**result, "replaced": exists}


@app.get("/api/flow/context", dependencies=[Depends(require_login)])
def flow_context(format: str = "json"):
    """Everything an AI needs to write a flow for this hub: format, nodes, your devices, rooms, examples.
    ?format=markdown returns it as a prompt to paste into an AI chat."""
    context = aicontext.build(hub, flows, store)
    return PlainTextResponse(aicontext.markdown(context)) if format == "markdown" else context


app.include_router(mcp.router(
    require_login,
    context=lambda: aicontext.markdown(aicontext.build(hub, flows, store)),
    devices=lambda: aicontext.devices(hub),
    flows=lambda: flows.summary(),
    validate=lambda text: aicontext.check(text, hub),
    import_flow=lambda text, replace: flow_import(ImportBody(yaml=text, replace=replace)),
))


@app.get("/api/flows", dependencies=[Depends(require_login)])
async def list_flows() -> list[dict]:
    return flows.summary()


@app.post("/api/flows", dependencies=[Depends(require_login)])
def create_flow(body: FlowBody) -> dict:
    return flows.create(body.name or "New flow", body.graph)


@app.get("/api/flows/{flow_id}", dependencies=[Depends(require_login)])
def get_flow(flow_id: str) -> dict:
    return _flow(flow_id)


@app.put("/api/flows/{flow_id}", dependencies=[Depends(require_login)])
def update_flow(flow_id: str, body: FlowBody) -> dict:
    _flow(flow_id)
    return flows.update(flow_id, body.name, body.graph, body.enabled)


@app.delete("/api/flows/{flow_id}", dependencies=[Depends(require_login)])
def delete_flow(flow_id: str) -> dict:
    _flow(flow_id)
    flows.delete(flow_id)
    return {"ok": True}


@app.post("/api/flows/{flow_id}/run/{node_id}", dependencies=[Depends(require_login)])
async def run_flow_node(flow_id: str, node_id: str) -> dict:
    flow = _flow(flow_id)
    if not any(n["id"] == node_id for n in flow["graph"].get("nodes", [])):
        raise HTTPException(404, "Unknown node")
    await flows.run_now(flow_id, node_id)
    return {"ok": True}


@app.post("/api/flows/{flow_id}/run", dependencies=[Depends(require_login)])
async def run_flow(flow_id: str) -> dict:
    _flow(flow_id)
    return {"started": await flows.run_flow(flow_id)}


class ControlBody(BaseModel):
    value: bool | float | str | None = None


@app.post("/api/flows/{flow_id}/controls/{control_id}", dependencies=[Depends(require_login)])
def use_control(flow_id: str, control_id: str, body: ControlBody) -> dict:
    """Use a control of the flow's card (the dashboard calls this; a button needs no value)."""
    _flow(flow_id)
    try:
        return {"value": flows.set_control(flow_id, control_id, body.value)}
    except KeyError:
        raise HTTPException(404, "Unknown control")
    except ValueError as err:
        raise HTTPException(400, str(err))


@app.get("/api/flows/{flow_id}/activity", dependencies=[Depends(require_login)])
def flow_activity(flow_id: str) -> dict:
    _flow(flow_id)
    return flows.activity(flow_id)


@app.get("/api/flows/{flow_id}/log", dependencies=[Depends(require_login)])
def flow_log(flow_id: str) -> list[dict]:
    _flow(flow_id)
    return list(reversed(flows.logs.get(flow_id, [])))


# --- system -------------------------------------------------------------

@app.get("/api/system", dependencies=[Depends(require_login)])
async def system() -> dict:
    """One entry per integration with something to show, by its id (zigbee, matter, ...). The Integrations page shows it."""
    async def info(plugin):
        result = plugin.system_info(ADAPTERS.get(plugin.source))
        return await result if inspect.isawaitable(result) else result

    infos = await asyncio.gather(*(info(p) for p in PLUGINS), return_exceptions=True)
    out = {}
    for p, i in zip(PLUGINS, infos):
        if isinstance(i, Exception):  # one integration failing must not hide the others
            log.warning("%s: system info failed: %s", p.id, i)
        elif i is not None:
            out[p.id] = i
    return out


@app.post("/api/update/check", dependencies=[Depends(require_login)])
async def update_check() -> dict:
    return await updates.check()


@app.post("/api/update/install", dependencies=[Depends(require_login)])
async def update_install() -> dict:
    """Pulls the new image and restarts the hub into it; the page reloads when the hub is back."""
    try:
        await updates.install()
    except Exception as err:
        raise HTTPException(400, str(err))
    return {"ok": True}


@app.get("/api/variables", dependencies=[Depends(require_login)])
def variables() -> dict:
    return store.variables()


@app.post("/api/hook/{token}/{name}")
def webhook(token: str, name: str) -> dict:
    """For notification buttons: no login, the token in the URL is the secret."""
    import hmac
    if not hmac.compare_digest(token, store.hook_token()):
        raise HTTPException(404, "Not found")
    return {"fired": flows.webhook(name)}


@app.get("/api/notify", dependencies=[Depends(require_login)])
def notify_info() -> dict:
    # Behind login. Unlike `Field.secret` values, the ntfy topic is returned on purpose: the page shows it
    # so the user can subscribe their phone to it.
    return {"configured": notify.configured(), "server": config.NTFY_URL, "topic": config.NTFY_TOPIC,
            "app_connections": notify.app_clients()}


@app.post("/api/notify/test", dependencies=[Depends(require_login)])
async def notify_test() -> dict:
    try:
        used = await notify.send("Test from Noodle: notifications work.", "Noodle test")
    except Exception as err:
        raise HTTPException(400, str(err))
    return {"ok": True, **used}


# --- integrations: connect services from the web interface --------------------------------------

SHOWN = [p for p in PLUGINS if p.visible]


def _integrations() -> list[integrations.Integration]:
    return [p.describe(ADAPTERS.get(p.source)) for p in SHOWN]


def _plugin(integration_id: str):
    found = next((p for p in SHOWN if p.id == integration_id), None)
    if found is None:
        raise HTTPException(404, "Unknown integration")
    return found


def _integration(integration_id: str) -> integrations.Integration:
    plugin = _plugin(integration_id)
    return plugin.describe(ADAPTERS.get(plugin.source))


def _describe(item: integrations.Integration) -> dict:
    plugin = _plugin(item.id)
    data = integrations.describe(item, plugin, ADAPTERS.get(plugin.source))
    if plugin.searchable:
        data["searchable"], data["search"] = True, discovery.state(item.id)
    return data


@app.get("/api/integrations", dependencies=[Depends(require_login)])
def list_integrations() -> list[dict]:
    return [_describe(i) for i in _integrations()]


class SettingsBody(BaseModel):
    values: dict[str, str]


@app.put("/api/integrations/{integration_id}", dependencies=[Depends(require_login)])
async def save_integration(integration_id: str, body: SettingsBody) -> dict:
    item = _integration(integration_id)
    allowed = {f.key: f for f in item.fields}
    # A secret left empty keeps what is saved.
    values = {k: v for k, v in body.values.items() if k in allowed and not (allowed[k].secret and not v.strip())}
    try:
        config.save(values)
    except ValueError as err:
        raise HTTPException(400, f"One of the values is not valid: {err}")
    if "home_name" in values:
        hub.broadcast({"type": "home", "name": config.HOME_NAME})  # the sidebar and page title update
    if item.adapter and (not item.gated or item.id in integrations.added_ids()):  # one that is not added is not running
        await restart_adapter(item.adapter)
        await asyncio.sleep(2.5)  # give it a moment to connect, so the answer shows the result
    return _describe(item)


def _set_added(ids: list[str]) -> None:
    config.save({"integrations": ",".join(ids) or "none"})  # "none": an empty list would mean "work it out"


@app.post("/api/integrations/{integration_id}/add", dependencies=[Depends(require_login)])
async def add_integration(integration_id: str) -> dict:
    item = _integration(integration_id)
    ids = integrations.added_ids()
    if item.id not in ids:
        _set_added([*ids, item.id])
    if item.gated and item.adapter:
        await restart_adapter(item.adapter)
    return _describe(item)


@app.delete("/api/integrations/{integration_id}", dependencies=[Depends(require_login)])
async def remove_integration(integration_id: str) -> dict:
    item = _integration(integration_id)
    if item.always:
        raise HTTPException(400, "This one cannot be removed")
    _set_added([i for i in integrations.added_ids() if i != item.id])
    if item.gated and item.adapter and (task := tasks.pop(item.adapter, None)):
        task.cancel()  # stop reconnecting
    # Forget the connection details too (but keep defaults like the MQTT port).
    plugin = _plugin(item.id)
    if plugin.forget:
        config.save({key: "" for key in plugin.forget})
    plugin.on_remove(hub, ADAPTERS.get(plugin.source))
    if item.adapter and not item.gated:
        await restart_adapter(item.adapter)
    return _describe(item)


def _searchable(integration_id: str):
    plugin = _plugin(integration_id)
    adapter = ADAPTERS.get(plugin.source)
    if not plugin.searchable or adapter is None:
        raise HTTPException(404, "This integration has nothing to search for")
    if integration_id not in integrations.added_ids():
        raise HTTPException(400, "Add the integration first")
    return plugin, adapter


@app.post("/api/integrations/{integration_id}/search", dependencies=[Depends(require_login)])
async def start_search(integration_id: str) -> dict:
    """Look for new devices for half a minute. The progress is pushed over /api/ws."""
    plugin, adapter = _searchable(integration_id)
    return discovery.start(integration_id, lambda seconds, found: plugin.search(adapter, seconds, found))


@app.delete("/api/integrations/{integration_id}/search", dependencies=[Depends(require_login)])
async def stop_search(integration_id: str) -> dict:
    _searchable(integration_id)
    return discovery.stop(integration_id)


@app.post("/api/integrations/{integration_id}/found/{key}/add", dependencies=[Depends(require_login)])
async def add_found(integration_id: str, key: str) -> dict:
    plugin, adapter = _searchable(integration_id)
    try:
        await plugin.add_found(adapter, key)
    except PressButton as err:
        raise HTTPException(409, str(err) or plugin.press_hint)  # not an error: the page asks again
    except (KeyError, ValueError) as err:
        raise HTTPException(400, str(err.args[0]) if err.args else "Could not add that")
    except Exception as err:
        raise HTTPException(400, f"Could not add that: {err}")
    if plugin.restart_after_add and plugin.source:
        await restart_adapter(plugin.source)
        await asyncio.sleep(2.5)  # give it a moment to connect, so the answer shows the result
    discovery.mark_added(integration_id, key)
    return _describe(_integration(integration_id))


# Each plugin brings its own endpoints (pairing, discovery, ...).
_ctx = types.SimpleNamespace(
    require_login=require_login, restart_adapter=restart_adapter,
    describe=lambda integration_id: _describe(_integration(integration_id)))
for _p in PLUGINS:
    if _router := _p.routes(ADAPTERS.get(_p.source), _ctx):
        app.include_router(_router)


# --- phones (the Noodle app reports itself as a device) -----------------

class PhoneBody(BaseModel):
    name: str = Field(max_length=60)
    battery: int | None = Field(None, ge=0, le=100)
    charging: bool | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    accuracy: float | None = Field(None, ge=0)


@app.post("/api/phone/{phone_id}", dependencies=[Depends(require_login)])
def phone_report(phone_id: str, body: PhoneBody) -> dict:
    if not phone_id.replace("-", "").replace("_", "").isalnum() or len(phone_id) > 64:
        raise HTTPException(400, "Bad phone id")
    return {"home": phone.report(phone_id, **body.model_dump())}


# --- live updates -------------------------------------------------------

@app.websocket("/api/ws")
async def live(ws: WebSocket) -> None:
    token = _bearer(ws.headers, ws.query_params)
    if not ws.session.get("user") and not (token and store.check_app_token(token)):
        await ws.close(code=4401)
        return
    await ws.accept()
    global _app_clients
    is_app = not ws.session.get("user")  # the browser uses its login cookie, the app uses its token
    if is_app:
        _app_clients += 1
    await ws.send_json({"type": "snapshot", "devices": [d.as_dict() for d in hub.devices.values()],
                        "areas": store.areas(), "flow_issues": flows.file_issues,
                        "home_name": config.HOME_NAME})

    async def send(message: dict) -> None:
        await ws.send_json(message)

    hub.subscribe(send)
    try:
        while True:
            await ws.receive_text()  # keep the socket open; the client sends pings
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(send)
        if is_app:
            _app_clients -= 1


# --- interface (SvelteKit static build, SPA fallback) ------------------

if config.STATIC_DIR.exists():
    app.mount("/_app", StaticFiles(directory=config.STATIC_DIR / "_app"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        file = (config.STATIC_DIR / path).resolve()
        if path and file.is_file() and config.STATIC_DIR.resolve() in file.parents:
            return FileResponse(file, headers={"Cache-Control": "no-cache"})
        # Always fetch the page itself again, so a phone never keeps an old version of the interface.
        return FileResponse(config.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
