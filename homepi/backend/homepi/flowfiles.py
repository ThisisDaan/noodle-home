"""Flows as YAML files, one per flow, in <config>/flows/. The files are the source of truth: edit them by hand,
with an AI, or in the web editor, which writes them too. A file looks like this:

    id: deken-auto-off            # also the name of the flow in links and in 'Run another flow'
    name: Deken | Auto off after 2 hours
    enabled: true
    nodes:
      change:                     # the node's id; its settings sit next to its type
        type: trigger.state
        device_id: matter:4
        key: switch_1
        outputs: ['switch_1:on', 'switch_1:off']
      wait: {type: action.timer, minutes: 120}
    edges:                        # from an output of a node to an input of another
      - {from: change, out: 'switch_1:on', to: wait, in: start}
      - {from: change, out: 'switch_1:off', to: wait, in: stop}
    layout:                       # where the editor draws the nodes (optional)
      change: [0, 0]
      wait: [360, 0]

`out` defaults to "out" and `in` to the node's only input. `python -m homepi schema` prints the JSON Schema
of this format and `python -m homepi validate` checks files.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

from . import nodespec, plugins
from .yamlfile import new_yaml, plain

log = logging.getLogger(__name__)

TOP_KEYS = {"id", "name", "description", "enabled", "nodes", "edges", "layout"}
EDGE_KEYS = {"from", "out", "to", "in", "id"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SUFFIXES = (".yaml", ".yml")


# --- what nodes exist ------------------------------------------------------------------------------

def node_specs() -> dict[str, dict]:
    """type -> {label, category, help, fields: {name: (type, description[, allowed])}}, built-in and from plugins."""
    specs = {t: dict(s) for t, s in nodespec.CORE.items()}
    for node_type, (plugin, node) in plugins.node_types().items():
        fields: dict[str, tuple] = {}
        for f in node.fields:
            kind = {"number": "num", "buttons": "list"}.get(f.type, "str")
            fields[f.key] = (kind, f.label, [v for v, _ in f.options]) if f.type == "select" else (kind, f.label)
        for key in node.defaults:
            fields.setdefault(key, ("any", ""))
        specs[node_type] = {"label": node.label, "category": node.category, "help": f"Added by the {plugin.name if plugin else 'plugin'} integration.",
                            "fields": fields}
    return specs


# --- flow <-> plain document -----------------------------------------------------------------------

def default_edge_id(source: str, handle: str, target: str, to: str | None = None) -> str:
    return f"{source}-{handle}-{target}" + (f"-{to}" if to else "")


_plain = plain


def to_doc(flow: dict) -> dict:
    """The file content for a flow: {id, name, enabled, nodes, edges, layout}."""
    graph = flow.get("graph") or {}
    nodes: dict[str, dict] = {}
    layout: dict[str, list] = {}
    for n in graph.get("nodes", []):
        data = dict(n.get("data") or {})
        if "type" in data:
            raise ValueError(f"node {n['id']}: a setting named 'type' cannot be written to a file")
        nodes[str(n["id"])] = {"type": n.get("type", ""), **data}
        pos = n.get("position")
        if pos:
            layout[str(n["id"])] = [round(pos.get("x", 0)), round(pos.get("y", 0))]
    edges = []
    for e in graph.get("edges", []):
        out, to = e.get("sourceHandle") or "out", e.get("targetHandle")
        edge: dict[str, Any] = {"from": e["source"], **({"out": out} if out != "out" else {}), "to": e["target"],
                                **({"in": to} if to else {})}
        if e.get("id") and e["id"] != default_edge_id(e["source"], out, e["target"], to):
            edge["id"] = e["id"]
        edges.append(edge)
    return {"id": flow["id"], "name": flow["name"], "enabled": bool(flow.get("enabled")),
            "nodes": nodes, "edges": edges, "layout": layout}


def _auto_layout(nodes: list[str], edges: list[dict]) -> dict[str, list]:
    """Columns by distance from a start, for files that do not say where their nodes go."""
    depth = {n: 0 for n in nodes}
    for _ in range(len(nodes)):
        for e in edges:
            if e["from"] in depth and e["to"] in depth and depth[e["to"]] <= depth[e["from"]] < len(nodes):
                depth[e["to"]] = depth[e["from"]] + 1
    rows: dict[int, int] = {}
    out = {}
    for n in nodes:
        row = rows[depth[n]] = rows.get(depth[n], -1) + 1
        out[n] = [depth[n] * 360, row * 140]
    return out


def from_doc(doc: Mapping) -> dict:
    """A flow {id, name, enabled, graph} from a checked document (see validate)."""
    doc = _plain(doc)
    edges_in = doc.get("edges") or []
    layout = {str(k): v for k, v in (doc.get("layout") or {}).items()}
    ids = [str(k) for k in (doc.get("nodes") or {})]
    layout = {**_auto_layout(ids, [{"from": str(e["from"]), "to": str(e["to"])} for e in edges_in]), **layout}
    nodes = []
    for nid, body in (doc.get("nodes") or {}).items():
        data = {k: v for k, v in body.items() if k != "type"}
        x, y = layout[str(nid)]
        nodes.append({"id": str(nid), "type": body["type"], "position": {"x": x, "y": y}, "data": data})
    edges = []
    for e in edges_in:
        out, to = e.get("out") or "out", e.get("in")
        edges.append({"id": e.get("id") or default_edge_id(str(e["from"]), out, str(e["to"]), to),
                      "source": str(e["from"]), "sourceHandle": out, "target": str(e["to"]),
                      **({"targetHandle": to} if to else {})})
    return {"id": str(doc["id"]), "name": doc["name"], "enabled": bool(doc.get("enabled", False)),
            "graph": {"nodes": nodes, "edges": edges}}


def content_key(flow: dict) -> str:
    """Equal for flows that would be written as the same file."""
    return hashlib.sha1(json.dumps(to_doc(flow), sort_keys=True, default=str).encode()).hexdigest()


# --- checking --------------------------------------------------------------------------------------

def _fits(kind: str, value: Any) -> bool:
    if value is None or kind == "any":
        return True
    if kind == "str":
        return isinstance(value, str)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "list":
        return isinstance(value, (list, tuple))
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return kind == "num" or float(value).is_integer()
    try:  # the editor used to save some numbers as text
        float(value)
        return isinstance(value, str)
    except (TypeError, ValueError):
        return False


def validate(doc: Any) -> tuple[list[str], list[str]]:
    """(errors, warnings). A file with errors is not loaded."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(doc, Mapping):
        return ["The file must contain a mapping with id, name, nodes and edges"], []
    for key in doc:
        if key not in TOP_KEYS:
            errors.append(f"unknown key '{key}' (allowed: {', '.join(sorted(TOP_KEYS))})")
    if not isinstance(doc.get("id"), str) or not ID_RE.match(doc.get("id") or ""):
        errors.append("id must be text of letters, digits, '-', '_' or '.', e.g. kitchen-light-at-sunset")
    if not isinstance(doc.get("name"), str) or not doc["name"].strip():
        errors.append("name must be a non-empty text")
    if "enabled" in doc and not isinstance(doc["enabled"], bool):
        errors.append("enabled must be true or false")
    specs = node_specs()
    nodes = doc.get("nodes", {})
    node_ids: set[str] = set()
    if not isinstance(nodes, Mapping):
        errors.append("nodes must be a mapping of node id to settings")
        nodes = {}
    for raw_id, node in nodes.items():
        nid = str(raw_id)
        node_ids.add(nid)
        if not isinstance(node, Mapping) or not isinstance(node.get("type"), str):
            errors.append(f"node {nid}: needs a 'type'")
            continue
        spec = specs.get(node["type"])
        if spec is None:
            errors.append(f"node {nid}: unknown type '{node['type']}'")
            continue
        for key, value in node.items():
            if key == "type":
                continue
            field = spec["fields"].get(key)
            if field is None:
                warnings.append(f"node {nid}: '{key}' is not a setting of {node['type']} (ignored)")
            elif not _fits(field[0], value):
                errors.append(f"node {nid}: {key} must be {'a number' if field[0] == 'num' else 'a whole number' if field[0] == 'int' else 'a ' + field[0].replace('str', 'text')}, got {value!r}")
            elif len(field) > 2 and value is not None and value not in field[2]:
                errors.append(f"node {nid}: {key} must be one of {field[2]}, got {value!r}")
    edges = doc.get("edges", [])
    if not isinstance(edges, (list, tuple)):
        errors.append("edges must be a list")
        edges = []
    for i, edge in enumerate(edges, 1):
        if not isinstance(edge, Mapping):
            errors.append(f"edge {i}: must be a mapping like {{from: a, to: b}}")
            continue
        for key in edge:
            if key not in EDGE_KEYS:
                errors.append(f"edge {i}: unknown key '{key}' (allowed: from, out, to, in)")
        for end in ("from", "to"):
            if str(edge.get(end)) not in node_ids:
                errors.append(f"edge {i}: {end} '{edge.get(end)}' is not a node of this flow")
    layout = doc.get("layout", {})
    if not isinstance(layout, Mapping):
        errors.append("layout must be a mapping of node id to [x, y]")
    else:
        for nid, pos in layout.items():
            if str(nid) not in node_ids:
                warnings.append(f"layout: '{nid}' is not a node of this flow")
            elif not (isinstance(pos, (list, tuple)) and len(pos) == 2 and all(isinstance(v, (int, float)) for v in pos)):
                errors.append(f"layout: {nid} must be [x, y]")
    if nodes and not any(specs.get(n.get("type") if isinstance(n, Mapping) else None, {}).get("category") == "trigger"
                         for n in nodes.values()):
        warnings.append("the flow has no trigger, so nothing will start it")
    return errors, warnings


# --- JSON Schema -----------------------------------------------------------------------------------

_JSON_TYPES = {"str": {"type": "string"}, "num": {"type": ["number", "string"]}, "int": {"type": "integer"},
               "bool": {"type": "boolean"}, "list": {"type": "array"}, "any": {}}


def schema() -> dict:
    """JSON Schema of a flow file, with every node the installed integrations provide."""
    variants = []
    for node_type, spec in sorted(node_specs().items()):
        props: dict[str, Any] = {"type": {"const": node_type}}
        for key, field in spec["fields"].items():
            prop = dict(_JSON_TYPES[field[0]])
            if field[1]:
                prop["description"] = field[1]
            if len(field) > 2:
                prop["enum"] = list(field[2])
            props[key] = prop
        variants.append({"title": f"{spec['label']} ({node_type})", "description": spec["help"], "type": "object",
                         "required": ["type"], "properties": props, "additionalProperties": False})
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Noodle flow", "type": "object", "required": ["id", "name", "nodes"], "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "pattern": ID_RE.pattern},
            "name": {"type": "string", "minLength": 1},
            "description": {"type": "string"},
            "enabled": {"type": "boolean", "default": False,
                        "description": "New flows start switched off; switch them on in the app after checking them."},
            "nodes": {"type": "object", "additionalProperties": {"oneOf": variants}},
            "edges": {"type": "array", "items": {
                "type": "object", "required": ["from", "to"], "additionalProperties": False,
                "properties": {"from": {"type": "string"}, "out": {"type": "string", "default": "out"},
                               "to": {"type": "string"}, "in": {"type": "string"}, "id": {"type": "string"}}}},
            "layout": {"type": "object", "additionalProperties": {
                "type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}}}}


# --- files -----------------------------------------------------------------------------------------

_yaml = new_yaml


def _flow_map(values: Mapping) -> CommentedMap:
    m = CommentedMap(values)
    m.fa.set_flow_style()
    return m


def _flow_seq(values) -> CommentedSeq:
    s = CommentedSeq(values)
    s.fa.set_flow_style()
    return s


def parse(text: str) -> Any:
    return _yaml().load(text)


class FlowFiles:
    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.stamps: dict[str, tuple[int, int]] = {}  # file name -> (mtime_ns, size) when last read or written
        self.paths: dict[str, Path] = {}  # flow id -> its file
        self.written: dict[str, str] = {}  # flow id -> content_key of its file

    def _files(self) -> dict[str, Path]:
        try:
            return {p.name: p for p in sorted(self.dir.iterdir()) if p.suffix in SUFFIXES and p.is_file()}
        except OSError:
            return {}

    def scan(self) -> tuple[list[Path], list[Path]]:
        """(new or changed files, files that are gone) since the last read or write."""
        now = self._files()
        changed = [p for name, p in now.items() if self.stamps.get(name) != self._stamp(p)]
        gone = [self.dir / name for name in self.stamps if name not in now]
        return changed, gone

    @staticmethod
    def _stamp(path: Path) -> tuple[int, int]:
        st = path.stat()
        return (st.st_mtime_ns, st.st_size)

    def read(self, path: Path) -> tuple[dict | None, list[str], list[str]]:
        """(flow, errors, warnings) of one file; flow is None when it has errors."""
        try:
            self.stamps[path.name] = self._stamp(path)
            doc = parse(path.read_text(encoding="utf-8"))
        except (OSError, YAMLError, UnicodeDecodeError) as err:
            return None, [str(err).strip().splitlines()[0] if str(err).strip() else type(err).__name__], []
        errors, warnings = validate(doc)
        if errors:
            return None, errors, warnings
        return from_doc(doc), [], warnings

    def read_all(self) -> list[tuple[Path, dict | None, list[str], list[str]]]:
        return [(p, *self.read(p)) for p in self._files().values()]

    def attach(self, flow: dict, path: Path) -> None:
        """Remember that this flow lives in this file and that the file holds this content."""
        self.paths[flow["id"]] = path
        self.written[flow["id"]] = content_key(flow)

    def id_for(self, path: Path) -> str | None:
        return next((i for i, p in self.paths.items() if p == path), None)

    def in_sync(self, flow: dict) -> bool:
        return self.written.get(flow["id"]) == content_key(flow) and self.paths.get(flow["id"], Path()).exists()

    def write(self, flow: dict) -> Path:
        """Write the flow's file, keeping the comments and order of the file that is there."""
        new = to_doc(flow)
        path = self.paths.get(flow["id"]) or self.dir / f"{flow['id']}.yaml"
        yaml = _yaml()
        current = None
        if path.exists():
            try:
                current = yaml.load(path.read_text(encoding="utf-8"))
            except (OSError, YAMLError):
                current = None
        doc = current if isinstance(current, CommentedMap) else CommentedMap()
        for key in ("id", "name", "enabled"):
            doc[key] = new[key]
        nodes = doc.get("nodes") if isinstance(doc.get("nodes"), CommentedMap) else CommentedMap()
        for nid in [k for k in nodes if str(k) not in new["nodes"]]:
            del nodes[nid]
        for nid, body in new["nodes"].items():
            old = nodes.get(nid)
            if not isinstance(old, CommentedMap):
                old = nodes[nid] = _flow_map(body) if len(body) <= 3 and all(
                    not isinstance(v, (dict, list)) for v in body.values()) else CommentedMap(body)
                continue
            for key in [k for k in old if k not in body]:
                del old[key]
            for key, value in body.items():
                if _plain(old.get(key)) != value or key not in old:
                    old[key] = value
        doc["nodes"] = nodes
        doc["edges"] = CommentedSeq(_flow_map(e) for e in new["edges"])  # one line per edge
        doc["layout"] = CommentedMap({k: _flow_seq(v) for k, v in new["layout"].items()})
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            yaml.dump(doc, f)
        os.replace(tmp, path)
        self.attach(flow, path)
        self.stamps[path.name] = self._stamp(path)
        return path

    def remove(self, flow_id: str) -> None:
        path = self.paths.pop(flow_id, None)
        self.written.pop(flow_id, None)
        if path:
            self.stamps.pop(path.name, None)
            try:
                path.unlink()
            except FileNotFoundError:
                pass


# --- command line: python -m homepi validate | schema ----------------------------------------------

def cli(args: list[str], default_dir: Path) -> int:
    import sys

    if args[:1] == ["schema"]:
        print(json.dumps(schema(), indent=2))
        return 0
    paths: list[Path] = []
    for arg in args[1:] or [str(default_dir)]:
        p = Path(arg)
        paths += sorted(q for q in p.iterdir() if q.suffix in SUFFIXES) if p.is_dir() else [p]
    if not paths:
        print(f"No flow files in {default_dir}")
        return 0
    bad, seen = 0, {}
    files = FlowFiles(default_dir)
    for path in paths:
        flow, errors, warnings = files.read(path)
        if flow and flow["id"] in seen:
            errors.append(f"id '{flow['id']}' is already used by {seen[flow['id']]}")
        elif flow:
            seen[flow["id"]] = path.name
        for line in errors:
            print(f"{path.name}: error: {line}", file=sys.stderr)
        for line in warnings:
            print(f"{path.name}: warning: {line}", file=sys.stderr)
        bad += bool(errors)
        if not errors and not warnings:
            print(f"{path.name}: ok")
    return 1 if bad else 0
