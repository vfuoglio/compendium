"""MCP server: a small, source-agnostic tool set over any configured sources."""
from __future__ import annotations

import argparse
import functools
import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations

from .config import find_config, load_config, sources_from_dirs
from .core import SourceError
from .hub import Hub

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
ADDITIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)


def _expose_errors(exc_type):
    """Turn SourceError into an SDK error whose message the model can read.

    Other exceptions are left alone, so genuine crashes stay generic to the client.
    """

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except SourceError as e:
                raise exc_type(str(e)) from e

        return wrapper

    return decorate


tool_errors = _expose_errors(ToolError)
resource_errors = _expose_errors(ResourceError)


def _instructions(hub: Hub) -> str:
    lines = [f"- {d['name']} ({d['type']}{'' if not d['read_only'] else ', read-only'})"
             for d in hub.describe()]
    text = (
        "Access to the user's personal knowledge sources:\n"
        + "\n".join(lines)
        + "\n\nItems are addressed by a ref like 'source:id' (e.g. 'notes:projects/web.md'). "
        "Start with search or list_items, then read_item for full content. Cite refs when you "
        "use their content."
    )
    if hub.any_writable:
        text += (
            " Write tools only ever add content: they never overwrite or delete. Prefer "
            "append_to_item over creating near-duplicates."
        )
    return text


def create_server(hub: Hub) -> MCPServer:
    mcp = MCPServer("compendium", instructions=_instructions(hub))

    @mcp.tool(annotations=READ)
    def list_sources() -> list[dict]:
        """List the configured knowledge sources: name, type, whether writable, and
        whether they support links."""
        return hub.describe()

    @mcp.tool(annotations=READ)
    @tool_errors
    def search(query: str, source: str | None = None, limit: int = 10) -> list[dict]:
        """Search all sources (or just one, via `source`) and return ranked results with
        snippets. Each result has a `ref` to pass to read_item. Matches in titles and tags
        rank higher, as do items matching more of the query's words."""
        return hub.search(query, source, limit)

    @mcp.tool(annotations=READ)
    @tool_errors
    def list_items(source: str | None = None, tag: str | None = None,
                   folder: str | None = None, limit: int = 50) -> list[dict]:
        """List items (ref, title, kind, tags, modified), newest first. Filter by source,
        tag (without '#'), or folder prefix such as 'projects'."""
        return hub.list_items(source, tag, folder, limit)

    @mcp.tool(annotations=READ)
    @tool_errors
    def read_item(ref: str) -> str:
        """Return the full content of one item by its ref, e.g. 'notes:projects/web.md'
        or 'books:library.csv#3' for a CSV row."""
        return hub.read(ref)

    if hub.any_links:

        @mcp.tool(annotations=READ)
        @tool_errors
        def find_links(ref: str) -> list[dict]:
            """List items that link to the given item (for example Markdown [[wikilinks]]).
            Useful for discovering related context."""
            return hub.links(ref)

    if hub.any_writable:

        @mcp.tool(annotations=ADDITIVE)
        @tool_errors
        def create_item(source: str, path: str, content: str) -> str:
            """Create a new item in a writable source. Fails if it already exists. Returns the
            new ref."""
            return hub.create(source, path, content)

        @mcp.tool(annotations=ADDITIVE)
        @tool_errors
        def append_to_item(ref: str, text: str) -> str:
            """Append text to the end of an existing item in a writable source. Existing
            content is untouched. Returns the ref."""
            return hub.append(ref, text)

    @mcp.resource("compendium://{source}/{+path}", mime_type="text/plain")
    @resource_errors
    def item_resource(source: str, path: str) -> str:
        """An item addressed by URI, e.g. compendium://notes/projects/web.md."""
        return hub.read(f"{source}:{path}")

    @mcp.prompt()
    def weekly_review(source: str = "", tag: str = "") -> str:
        """Summarise recently changed items into a weekly review."""
        args = []
        if source:
            args.append(f"source={source!r}")
        if tag:
            args.append(f"tag={tag.lstrip('#')!r}")
        call = f"list_items({', '.join(args)})" if args else "list_items"
        return (
            f"Use {call} to find my most recently modified items, read the newest ones, and write "
            "a weekly review: what I worked on, open questions, and suggested next steps. "
            "Cite refs."
        )

    return mcp


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="compendium", description="MCP server for your notes, documents and data."
    )
    p.add_argument("--config", help="path to a compendium.toml (default: ./compendium.toml, "
                   "~/.config/compendium/config.toml, or $COMPENDIUM_CONFIG)")
    p.add_argument("--dir", action="append", default=[], metavar="FOLDER",
                   help="quick start: serve a Markdown folder (repeatable)")
    p.add_argument("--writable", action="store_true",
                   help="with --dir: allow create/append (read-only by default)")
    a = p.parse_args(argv)

    try:
        if a.dir:
            sources = sources_from_dirs(a.dir, writable=a.writable)
        else:
            cfg = find_config(a.config)
            if cfg is None:
                raise SourceError(
                    "No sources configured. Create a compendium.toml, pass --config, or use "
                    "--dir FOLDER for a quick start."
                )
            sources = load_config(cfg)
        server = create_server(Hub(sources))
    except SourceError as e:
        print(f"compendium: {e}", file=sys.stderr)
        raise SystemExit(2) from None
    server.run()


if __name__ == "__main__":
    main()
