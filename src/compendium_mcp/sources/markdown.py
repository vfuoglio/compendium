"""Markdown folder source (Obsidian-style vaults work): tags, wikilinks, safe writes."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import (
    MAX_READ_CHARS, Hit, Item, Source, SourceError, check_options, make_snippet,
    resolve_in_root, score_text, walk_files,
)

SUFFIXES = {".md"}
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
INLINE_TAG = re.compile(r"(?<![\w/])#([A-Za-z][\w/-]*)")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def _frontmatter_tags(text: str) -> list[str]:
    m = FRONTMATTER.match(text)
    if not m:
        return []
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "tags":
            value = value.strip().strip("[]")
            return [t.strip().strip("'\"").lstrip("#") for t in value.split(",") if t.strip()]
    return []


def parse_tags(text: str) -> list[str]:
    body = FRONTMATTER.sub("", text, count=1)
    body = re.sub(r"```.*?```", "", body, flags=re.DOTALL)  # ignore code blocks
    return sorted({t.lower() for t in _frontmatter_tags(text) + INLINE_TAG.findall(body)})


def parse_title(text: str, fallback: str) -> str:
    for line in FRONTMATTER.sub("", text, count=1).splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


class MarkdownSource(Source):
    type_name = "markdown"
    supports_links = True
    supports_write = True

    def __init__(self, name: str, root: Path, read_only: bool = True):
        super().__init__(name, read_only)
        self.root = root.expanduser().resolve()
        if not self.root.is_dir():
            raise SourceError(f"Source '{name}': folder does not exist: {self.root}")

    @classmethod
    def from_config(cls, name: str, cfg: dict[str, Any], base: Path) -> "MarkdownSource":
        check_options(name, cfg, {"type", "path", "read_only"})
        if "path" not in cfg:
            raise SourceError(f"Source '{name}': 'path' is required.")
        return cls(name, base / Path(cfg["path"]).expanduser(), cfg.get("read_only", True))

    # ---- helpers ---------------------------------------------------------
    def _path(self, rel: str, must_exist: bool = True) -> Path:
        return resolve_in_root(self.root, rel, SUFFIXES, must_exist)

    def _rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    @staticmethod
    def _text(p: Path) -> str:
        return p.read_text(encoding="utf-8", errors="replace")

    def _item(self, p: Path, text: str | None = None) -> Item:
        text = self._text(p) if text is None else text
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        return Item(
            self._rel(p), parse_title(text, p.stem), "note", parse_tags(text),
            mtime.isoformat(timespec="seconds"),
        )

    # ---- reads -----------------------------------------------------------
    def list(self, tag=None, folder=None) -> list[Item]:
        tag = tag.lstrip("#").lower() if tag else None
        prefix = folder.strip("/") + "/" if folder else ""
        out = []
        for p in walk_files(self.root, SUFFIXES):
            if prefix and not self._rel(p).startswith(prefix):
                continue
            item = self._item(p)
            if tag and tag not in item.tags:
                continue
            out.append(item)
        return sorted(out, key=lambda i: i.modified, reverse=True)

    def read(self, item_id: str) -> str:
        p = self._path(item_id)
        text = self._text(p)
        if len(text) > MAX_READ_CHARS:
            raise SourceError(f"Note is larger than {MAX_READ_CHARS} characters; refusing to read.")
        return text

    def search(self, terms: list[str], limit: int) -> list[Hit]:
        hits = []
        for p in walk_files(self.root, SUFFIXES):
            text = self._text(p)
            item = self._item(p, text)
            score = score_text(terms, item.title, item.tags, text)
            if score:
                body = FRONTMATTER.sub("", text, count=1)
                hits.append(Hit(item.id, item.title, score, make_snippet(body, terms), "note"))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def links(self, item_id: str) -> list[Item]:
        """Notes linking to this one via [[wikilinks]] (by title or file name)."""
        target = self._path(item_id)
        names = {target.stem.lower(), parse_title(self._text(target), target.stem).lower()}
        out = []
        for p in walk_files(self.root, SUFFIXES):
            if p == target:
                continue
            text = self._text(p)
            if {m.strip().lower() for m in WIKILINK.findall(text)} & names:
                out.append(self._item(p, text))
        return out

    # ---- writes (additive only) -----------------------------------------
    def create(self, item_id: str, content: str) -> str:
        self.check_writable()
        p = self._path(item_id, must_exist=False)
        if p.exists():
            raise SourceError(f"Note already exists: {item_id}. Use append_to_item to add to it.")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        return self._rel(p)

    def append(self, item_id: str, text: str) -> str:
        self.check_writable()
        p = self._path(item_id)
        current = self._text(p)
        sep = "" if current.endswith("\n\n") else ("\n" if current.endswith("\n") else "\n\n")
        p.write_text(current + sep + text.rstrip("\n") + "\n", encoding="utf-8")
        return self._rel(p)
