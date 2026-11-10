"""CSV source: every row is an item. Point it at one .csv file or a folder of them."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import (
    Hit, Item, Source, SourceError, check_options, make_snippet, resolve_in_root,
    score_text, walk_files,
)

SUFFIXES = {".csv"}


class CsvSource(Source):
    """Item ids look like 'books.csv#3' (file, then 1-based data row)."""

    type_name = "csv"
    extra_options = frozenset({"title_column", "delimiter"})

    def __init__(self, name: str, path: Path, title_column: str | None = None, delimiter: str = ","):
        super().__init__(name, True)
        self.path = path.expanduser().resolve()
        if not self.path.exists():
            raise SourceError(f"Source '{name}': path does not exist: {self.path}")
        self.root = self.path.parent if self.path.is_file() else self.path
        self.title_column = title_column
        self.delimiter = delimiter
        self._cache: dict[Path, tuple[float, list[str], list[list[str]]]] = {}

    @classmethod
    def from_config(cls, name: str, cfg: dict[str, Any], base: Path) -> "CsvSource":
        check_options(name, cfg, {"type", "path", "read_only", "title_column", "delimiter"})
        if "path" not in cfg:
            raise SourceError(f"Source '{name}': 'path' is required.")
        return cls(name, base / Path(cfg["path"]).expanduser(), cfg.get("title_column"),
                   cfg.get("delimiter", ","))

    def _files(self) -> list[Path]:
        return [self.path] if self.path.is_file() else walk_files(self.root, SUFFIXES)

    def _table(self, p: Path) -> tuple[list[str], list[list[str]]]:
        mtime = p.stat().st_mtime
        cached = self._cache.get(p)
        if cached and cached[0] == mtime:
            return cached[1], cached[2]
        with p.open(newline="", encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.reader(f, delimiter=self.delimiter))
        header, body = (rows[0], rows[1:]) if rows else ([], [])
        self._cache[p] = (mtime, header, body)
        return header, body

    def _title(self, header: list[str], row: list[str]) -> str:
        if self.title_column and self.title_column in header:
            i = header.index(self.title_column)
        else:
            i = 0
        return row[i] if i < len(row) and row[i] else "(untitled)"

    def _id(self, p: Path, n: int) -> str:
        return f"{p.relative_to(self.root).as_posix()}#{n}"

    def _locate(self, item_id: str) -> tuple[Path, int]:
        file_part, sep, num = item_id.rpartition("#")
        if not sep or not num.isdigit():
            raise SourceError("Row ids look like 'file.csv#3'.")
        p = resolve_in_root(self.root, file_part, SUFFIXES)
        if self.path.is_file() and p != self.path:
            raise SourceError(f"Not found: {item_id}")
        return p, int(num)

    @staticmethod
    def _render(header: list[str], row: list[str]) -> str:
        return "\n".join(f"{h}: {v}" for h, v in zip(header, row))

    def list(self, tag=None, folder=None) -> list[Item]:
        if tag:
            return []
        prefix = folder.strip("/") if folder else ""
        out = []
        for p in self._files():
            if prefix and not p.relative_to(self.root).as_posix().startswith(prefix):
                continue
            header, body = self._table(p)
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
            out += [Item(self._id(p, n), self._title(header, r), "row", [], mtime)
                    for n, r in enumerate(body, 1)]
        return out

    def read(self, item_id: str) -> str:
        p, n = self._locate(item_id)
        header, body = self._table(p)
        if not 1 <= n <= len(body):
            raise SourceError(f"Row {n} does not exist (file has {len(body)} data rows).")
        return self._render(header, body[n - 1])

    def search(self, terms: list[str], limit: int) -> list[Hit]:
        hits = []
        for p in self._files():
            header, body = self._table(p)
            for n, row in enumerate(body, 1):
                title = self._title(header, row)
                text = self._render(header, row)
                score = score_text(terms, title, [], text)
                if score:
                    hits.append(Hit(self._id(p, n), title, score, make_snippet(text, terms), "row"))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]
