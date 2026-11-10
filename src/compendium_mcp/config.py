"""Load sources from a TOML config file (or build them from plain folders)."""
from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from .core import Source, SourceError
from .sources import SOURCE_TYPES, MarkdownSource

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DEFAULT_LOCATIONS = [Path("compendium.toml"), Path("~/.config/compendium/config.toml")]


def build_sources(raw: dict, base: Path) -> dict[str, Source]:
    tables = raw.get("sources")
    if not isinstance(tables, dict) or not tables:
        raise SourceError("Config has no [sources.<name>] tables.")
    sources: dict[str, Source] = {}
    for name, cfg in tables.items():
        if not NAME.match(name):
            raise SourceError(f"Invalid source name '{name}': use lowercase letters, digits, - and _.")
        if not isinstance(cfg, dict) or "type" not in cfg:
            raise SourceError(f"Source '{name}' needs a 'type'. Known: {sorted(SOURCE_TYPES)}")
        cls = SOURCE_TYPES.get(cfg["type"])
        if cls is None:
            raise SourceError(f"Source '{name}': unknown type '{cfg['type']}'. Known: {sorted(SOURCE_TYPES)}")
        sources[name] = cls.from_config(name, cfg, base)
    return sources


def load_config(path: str | Path) -> dict[str, Source]:
    p = Path(path).expanduser().resolve()
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SourceError(f"Config file not found: {p}") from None
    except tomllib.TOMLDecodeError as e:
        raise SourceError(f"Invalid TOML in {p}: {e}") from None
    return build_sources(raw, p.parent)


def sources_from_dirs(dirs: list[str], writable: bool = False) -> dict[str, Source]:
    """Quick start: treat each folder as a Markdown source named after the folder."""
    out: dict[str, Source] = {}
    for d in dirs:
        path = Path(d).expanduser().resolve()
        name = re.sub(r"[^a-z0-9_-]+", "-", path.name.lower()).strip("-") or "notes"
        base, i = name, 2
        while name in out:
            name, i = f"{base}-{i}", i + 1
        out[name] = MarkdownSource(name, path, read_only=not writable)
    return out


def find_config(explicit: str | None = None) -> Path | None:
    """Locate the config: --config, then $COMPENDIUM_CONFIG, then the default locations.

    An explicitly requested file that does not exist is an error, not a fall-through.
    """
    requested = explicit or os.environ.get("COMPENDIUM_CONFIG")
    if requested:
        p = Path(requested).expanduser()
        if not p.is_file():
            raise SourceError(f"Config file not found: {p}")
        return p
    for c in DEFAULT_LOCATIONS:
        p = c.expanduser()
        if p.is_file():
            return p
    return None
