"""One YAML file the user may edit by hand and the app also writes. Saving merges into what is on disk, so
comments and the order of keys survive. Imports nothing from the app, so config.py can use it."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError


def new_yaml() -> YAML:
    yaml = YAML()  # round trip: keeps comments; YAML 1.2, so `off` and `no` stay text
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 200
    yaml.allow_unicode = True
    return yaml


def plain(value: Any) -> Any:
    """ruamel's commented containers and scalars as ordinary Python values."""
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return str(value)


def _is_leaf(value: Any) -> bool:
    return isinstance(value, Mapping) and not any(isinstance(v, (Mapping, list, tuple)) for v in value.values())


def _convert(value: Any, depth: int) -> Any:
    """Plain data as YAML nodes: short lists and small maps deeper down on one line, the rest in blocks."""
    if isinstance(value, Mapping):
        m = CommentedMap((k, _convert(v, depth + 1)) for k, v in value.items())
        if depth >= 2 and _is_leaf(value):
            m.fa.set_flow_style()
        return m
    if isinstance(value, (list, tuple)):
        s = CommentedSeq(_convert(v, depth + 1) for v in value)
        if len(value) <= 8 and all(not isinstance(v, (Mapping, list, tuple)) and len(str(v)) <= 24 for v in value):
            s.fa.set_flow_style()
        return s
    return value


def _merge(target: CommentedMap, values: Mapping, replace: bool, depth: int, sections: bool = False) -> None:
    for key, value in values.items():
        current = target.get(key)
        # sections=True: top-level keys are sections (settings.yaml), so a section holding only plain values is still merged
        if isinstance(value, Mapping) and isinstance(current, CommentedMap) and (not _is_leaf(value) or (sections and depth == 0)):
            _merge(current, value, replace, depth + 1)
        elif key not in target or plain(current) != value:
            target[key] = _convert(value, depth + 1)
    if replace:
        for key in [k for k in target if k not in values]:
            del target[key]


class YamlFile:
    def __init__(self, path: Path, private: bool = False) -> None:
        self.path = path
        self.private = private  # only the owner may read it (secrets)
        self._stamp: tuple[int, int] | None = None

    def _current_stamp(self) -> tuple[int, int] | None:
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def exists(self) -> bool:
        return self.path.exists()

    def read(self) -> dict:
        """What the file holds as plain data; empty when it is missing. Raises ValueError for text that is not valid."""
        self._stamp = self._current_stamp()
        if self._stamp is None:
            return {}
        try:
            doc = new_yaml().load(self.path.read_text(encoding="utf-8"))
        except (OSError, YAMLError, UnicodeDecodeError) as err:
            raise ValueError(f"{self.path.name}: {str(err).strip().splitlines()[0] if str(err).strip() else err}") from err
        if doc is None:
            return {}
        if not isinstance(doc, Mapping):
            raise ValueError(f"{self.path.name}: must be a mapping of names to values")
        return plain(doc)

    def changed(self) -> bool:
        """Edited, created or removed since the app last read or wrote it."""
        return self._current_stamp() != self._stamp

    def write(self, values: Mapping, replace: bool = False, sections: bool = False, whole: tuple[str, ...] = ()) -> None:
        """Put values in the file. replace=True makes the file hold exactly these values; otherwise other keys stay.
        sections=True keeps the other keys inside each top-level section too."""
        yaml = new_yaml()
        doc = None
        if self.path.exists():
            try:
                doc = yaml.load(self.path.read_text(encoding="utf-8"))
            except (OSError, YAMLError, UnicodeDecodeError):
                doc = None
        if not isinstance(doc, CommentedMap):
            doc = CommentedMap()
        for key in whole:  # these top-level keys are written as given: what is not in them any more is gone
            if key in values and key in doc:
                del doc[key]
        _merge(doc, values, replace, 0, sections)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            yaml.dump(doc, f)
        if self.private:
            try:
                tmp.chmod(0o600)
            except OSError:
                pass  # not supported on this system
        os.replace(tmp, self.path)
        self._stamp = self._current_stamp()
