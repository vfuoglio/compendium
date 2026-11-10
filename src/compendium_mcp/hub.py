"""Combines sources behind one interface. References look like 'source:item-id'."""
from __future__ import annotations

from dataclasses import asdict

from .core import Hit, Item, Source, SourceError, query_terms


class Hub:
    def __init__(self, sources: dict[str, Source]):
        if not sources:
            raise SourceError("At least one source is required.")
        self.sources = sources

    @property
    def any_writable(self) -> bool:
        return any(s.writable for s in self.sources.values())

    @property
    def any_links(self) -> bool:
        return any(s.supports_links for s in self.sources.values())

    def source(self, name: str) -> Source:
        try:
            return self.sources[name]
        except KeyError:
            raise SourceError(f"Unknown source '{name}'. Available: {sorted(self.sources)}") from None

    def split_ref(self, ref: str) -> tuple[Source, str]:
        name, sep, item_id = ref.partition(":")
        if sep and name in self.sources:
            return self.sources[name], item_id
        if len(self.sources) == 1:  # lenient: bare id when there is only one source
            return next(iter(self.sources.values())), ref
        raise SourceError(
            f"Reference '{ref}' must look like 'source:id'. Available sources: {sorted(self.sources)}"
        )

    @staticmethod
    def _item(src: Source, i: Item) -> dict:
        d = asdict(i)
        d["ref"] = f"{src.name}:{i.id}"
        d["source"] = src.name
        d.pop("id")
        return d

    @staticmethod
    def _hit(src: Source, h: Hit) -> dict:
        d = asdict(h)
        d["ref"] = f"{src.name}:{h.id}"
        d["source"] = src.name
        d.pop("id")
        return d

    def describe(self) -> list[dict]:
        return [
            {
                "name": s.name, "type": s.type_name, "read_only": not s.writable,
                "supports_links": s.supports_links,
            }
            for s in self.sources.values()
        ]

    def search(self, query: str, source: str | None = None, limit: int = 10) -> list[dict]:
        terms = query_terms(query)
        limit = max(1, min(limit, 50))
        chosen = [self.source(source)] if source else list(self.sources.values())
        hits = [self._hit(s, h) for s in chosen for h in s.search(terms, limit)]
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:limit]

    def list_items(self, source: str | None = None, tag: str | None = None,
                   folder: str | None = None, limit: int = 50) -> list[dict]:
        limit = max(1, min(limit, 200))
        chosen = [self.source(source)] if source else list(self.sources.values())
        items = [self._item(s, i) for s in chosen for i in s.list(tag, folder)]
        items.sort(key=lambda d: d["modified"], reverse=True)
        return items[:limit]

    def read(self, ref: str) -> str:
        src, item_id = self.split_ref(ref)
        return src.read(item_id)

    def links(self, ref: str) -> list[dict]:
        src, item_id = self.split_ref(ref)
        return [self._item(src, i) for i in src.links(item_id)]

    def create(self, source: str, path: str, content: str) -> str:
        src = self.source(source)
        return f"{src.name}:{src.create(path, content)}"

    def append(self, ref: str, text: str) -> str:
        src, item_id = self.split_ref(ref)
        return f"{src.name}:{src.append(item_id, text)}"
