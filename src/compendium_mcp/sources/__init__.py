"""Registry of source types. Add a new kind of source by registering it here."""
from __future__ import annotations

from ..core import Source
from .csvsource import CsvSource
from .files import FilesSource
from .markdown import MarkdownSource

SOURCE_TYPES: dict[str, type[Source]] = {
    cls.type_name: cls for cls in (MarkdownSource, FilesSource, CsvSource)
}

__all__ = ["SOURCE_TYPES", "MarkdownSource", "FilesSource", "CsvSource"]
