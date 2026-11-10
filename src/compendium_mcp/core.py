"""The Source interface and shared types. No MCP dependency.

To add a new kind of knowledge source, subclass `Source`, implement the
read-side methods, and register it in `compendium_mcp.sources.SOURCE_TYPES`.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

MAX_READ_CHARS = 200_000


class SourceError(ValueError):
    """A problem the caller can understand and fix (bad path, not found...)."""


@dataclass(frozen=True)
class Item:
    id: str  # unique within its source; for file sources, a relative path
    title: str
    kind: str = ""  # e.g. "note", "pdf", "row"
    tags: list[str] = field(default_factory=list)
    modified: str = ""  # ISO 8601 UTC, when known


@dataclass(frozen=True)
class Hit:
    id: str
    title: str
    score: float
    snippet: str
    kind: str = ""


class Source(ABC):
    """A named collection of readable items.

    Capabilities beyond list/read/search are opt-in: override `links` and set
    `supports_links`, or override `create`/`append` and set `supports_write`.
    Sources are read-only unless configured otherwise.
    """

    type_name: ClassVar[str]
    supports_links: ClassVar[bool] = False
    supports_write: ClassVar[bool] = False
    # Config keys this type understands, beyond "type", "path" and "read_only".
    extra_options: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, name: str, read_only: bool = True):
        self.name = name
        self.read_only = read_only

    @classmethod
    @abstractmethod
    def from_config(cls, name: str, cfg: dict[str, Any], base: Path) -> "Source":
        """Build from a parsed config table; `base` is the config file's folder."""

    @property
    def writable(self) -> bool:
        return self.supports_write and not self.read_only

    @abstractmethod
    def list(self, tag: str | None = None, folder: str | None = None) -> list[Item]: ...

    @abstractmethod
    def read(self, item_id: str) -> str: ...

    @abstractmethod
    def search(self, terms: list[str], limit: int) -> list[Hit]:
        """Return hits for pre-tokenised lowercase terms, best first."""

    def links(self, item_id: str) -> list[Item]:
        raise SourceError(f"Source '{self.name}' ({self.type_name}) does not support links.")

    def create(self, item_id: str, content: str) -> str:
        raise SourceError(f"Source '{self.name}' is read-only or does not support writing.")

    def append(self, item_id: str, text: str) -> str:
        raise SourceError(f"Source '{self.name}' is read-only or does not support writing.")

    def check_writable(self) -> None:
        if not self.writable:
            raise SourceError(
                f"Source '{self.name}' is read-only. Set read_only = false in the config to allow writes."
            )


def resolve_in_root(root: Path, rel: str, suffixes: set[str], must_exist: bool = True) -> Path:
    """Resolve a caller-supplied relative path safely inside root.

    Rejects traversal and symlink escapes, hidden files/folders, and unexpected
    file types.
    """
    if not rel or "\x00" in rel:
        raise SourceError("Empty or invalid path.")
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise SourceError("Path escapes the source folder.")
    if p.suffix.lower() not in suffixes:
        raise SourceError(f"Unsupported file type. Allowed: {', '.join(sorted(suffixes))}")
    if any(part.startswith(".") for part in p.relative_to(root).parts):
        raise SourceError("Hidden files and folders are not accessible.")
    if must_exist and not p.is_file():
        raise SourceError(f"Not found: {rel}")
    return p


def walk_files(root: Path, suffixes: set[str]) -> list[Path]:
    """Files under root with an allowed suffix, skipping hidden folders and escaping symlinks."""
    out = []
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in suffixes:
            continue
        rel_parts = p.relative_to(root).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        r = p.resolve()
        if p.is_file() and (r == root or root in r.parents):
            out.append(p)
    return out


# ---- shared search scoring --------------------------------------------------
def query_terms(query: str) -> list[str]:
    terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 1]
    if not terms:
        raise SourceError("Query has no searchable terms.")
    return terms


def score_text(terms: list[str], title: str, tags: list[str], body: str) -> float:
    """Relevance of one item. Title and tag matches count more; matching more of
    the query's terms beats matching one term many times. 0 means no match."""
    low, title_l = body.lower(), title.lower()
    score, matched = 0.0, 0
    for t in terms:
        n = low.count(t)
        if n:
            matched += 1
            score += 1 + min(n, 5) * 0.2
        if t in title_l:
            score += 3
        if t in tags:
            score += 2
    if matched == 0:
        return 0.0
    return round(score * matched / len(terms), 2)


def make_snippet(text: str, terms: list[str], width: int = 160) -> str:
    flat = " ".join(text.split())
    low = flat.lower()
    pos = min((i for i in (low.find(t) for t in terms) if i >= 0), default=0)
    start = max(0, pos - width // 3)
    return ("..." if start else "") + flat[start : start + width] + (
        "..." if start + width < len(flat) else ""
    )


def check_options(name: str, cfg: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(cfg) - allowed
    if unknown:
        raise SourceError(
            f"Source '{name}': unknown option(s) {sorted(unknown)}. Allowed: {sorted(allowed)}"
        )
