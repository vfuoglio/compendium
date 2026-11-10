"""Plain documents source: .txt, .pdf (pip install compendium-mcp[pdf]), .docx ([docx])."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import (
    MAX_READ_CHARS, Hit, Item, Source, SourceError, check_options, make_snippet,
    resolve_in_root, score_text, walk_files,
)

SUFFIXES = {".txt", ".pdf", ".docx"}


def extract_text(p: Path) -> str:
    suffix = p.suffix.lower()
    if suffix == ".txt":
        return p.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise SourceError("PDF support needs: pip install 'compendium-mcp[pdf]'") from None
        pages = PdfReader(str(p)).pages
        return "\n\n".join(f"[page {i}]\n{pg.extract_text() or ''}" for i, pg in enumerate(pages, 1))
    if suffix == ".docx":
        try:
            import docx
        except ImportError:
            raise SourceError("DOCX support needs: pip install 'compendium-mcp[docx]'") from None
        return "\n\n".join(par.text for par in docx.Document(str(p)).paragraphs if par.text.strip())
    raise SourceError(f"Unsupported file type: {suffix}")


class FilesSource(Source):
    type_name = "files"

    def __init__(self, name: str, root: Path, read_only: bool = True):
        super().__init__(name, True)  # this source never writes
        self.root = root.expanduser().resolve()
        if not self.root.is_dir():
            raise SourceError(f"Source '{name}': folder does not exist: {self.root}")
        self._cache: dict[Path, tuple[float, str]] = {}

    @classmethod
    def from_config(cls, name: str, cfg: dict[str, Any], base: Path) -> "FilesSource":
        check_options(name, cfg, {"type", "path", "read_only"})
        if "path" not in cfg:
            raise SourceError(f"Source '{name}': 'path' is required.")
        return cls(name, base / Path(cfg["path"]).expanduser())

    def _text(self, p: Path) -> str:
        """Extracted text, cached by modification time (PDF extraction is slow)."""
        mtime = p.stat().st_mtime
        cached = self._cache.get(p)
        if cached and cached[0] == mtime:
            return cached[1]
        text = extract_text(p)
        self._cache[p] = (mtime, text)
        return text

    def _item(self, p: Path) -> Item:
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        return Item(
            p.relative_to(self.root).as_posix(), p.stem, p.suffix.lstrip(".").lower(), [],
            mtime.isoformat(timespec="seconds"),
        )

    def list(self, tag=None, folder=None) -> list[Item]:
        if tag:
            return []  # documents carry no tags
        prefix = folder.strip("/") + "/" if folder else ""
        items = [
            self._item(p) for p in walk_files(self.root, SUFFIXES)
            if p.relative_to(self.root).as_posix().startswith(prefix)
        ]
        return sorted(items, key=lambda i: i.modified, reverse=True)

    def read(self, item_id: str) -> str:
        text = self._text(resolve_in_root(self.root, item_id, SUFFIXES))
        if len(text) > MAX_READ_CHARS:
            note = f"\n\n[truncated at {MAX_READ_CHARS} characters]"
            return text[:MAX_READ_CHARS] + note
        return text

    def search(self, terms: list[str], limit: int) -> list[Hit]:
        hits = []
        for p in walk_files(self.root, SUFFIXES):
            try:
                text = self._text(p)
            except SourceError:
                continue  # missing optional dependency: skip rather than fail the search
            except Exception:
                continue  # unreadable or corrupt file
            item = self._item(p)
            score = score_text(terms, item.title, [], text)
            if score:
                hits.append(Hit(item.id, item.title, score, make_snippet(text, terms), item.kind))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]
