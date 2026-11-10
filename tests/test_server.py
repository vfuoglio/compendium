"""End-to-end: a real MCP client talking to the server in-process."""
from mcp.client import Client

from compendium_mcp.config import sources_from_dirs
from compendium_mcp.hub import Hub
from compendium_mcp.server import create_server


def text_of(result) -> str:
    return "".join(b.text for b in result.content if getattr(b, "type", "") == "text")


async def test_full_tool_set_when_writable_and_links(hub):
    async with Client(create_server(hub)) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        instructions = c.instructions
    assert set(tools) == {
        "list_sources", "search", "list_items", "read_item",
        "find_links", "create_item", "append_to_item",
    }
    assert tools["search"].annotations.read_only_hint is True
    assert tools["create_item"].annotations.destructive_hint is False
    assert "notes (markdown)" in instructions and "books (csv, read-only)" in instructions


async def test_write_tools_absent_when_everything_read_only(example_dir):
    hub = Hub(sources_from_dirs([str(example_dir / "notes")]))
    async with Client(create_server(hub)) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert "create_item" not in names and "append_to_item" not in names
    assert "find_links" in names


async def test_search_and_read_across_sources(hub):
    async with Client(create_server(hub)) as c:
        found = await c.call_tool("search", {"query": "replication consistency"})
        row = await c.call_tool("read_item", {"ref": "books:books.csv#1"})
        doc = await c.call_tool("read_item", {"ref": "docs:meeting-2026-11-03.txt"})
    assert "books:books.csv#1" in text_of(found)
    assert "Martin Kleppmann" in text_of(row)
    assert "Priya will own" in text_of(doc)


async def test_expected_errors_reach_the_model(hub):
    async with Client(create_server(hub)) as c:
        bad = await c.call_tool("read_item", {"ref": "notes:../../etc/passwd.md"})
        ro = await c.call_tool("create_item", {"source": "docs", "path": "a.txt", "content": "x"})
        unknown = await c.call_tool("search", {"query": "x1", "source": "nope"})
    assert bad.is_error and "escapes" in text_of(bad)
    assert ro.is_error and "read-only" in text_of(ro)
    assert unknown.is_error and "Unknown source" in text_of(unknown)


async def test_write_then_read(hub, example_dir):
    async with Client(create_server(hub)) as c:
        r = await c.call_tool("create_item", {"source": "notes", "path": "new.md", "content": "# New"})
        dup = await c.call_tool("create_item", {"source": "notes", "path": "new.md", "content": "again"})
    assert not r.is_error and "notes:new.md" in text_of(r)
    assert (example_dir / "notes" / "new.md").read_text() == "# New\n"
    assert dup.is_error


async def test_resource_template_and_prompt(hub):
    async with Client(create_server(hub)) as c:
        templates = (await c.list_resource_templates()).resource_templates
        res = await c.read_resource("compendium://notes/Design Principles.md")
        nested = await c.read_resource("compendium://notes/projects/rag-experiments.md")
        got = await c.get_prompt("weekly_review", {"source": "notes", "tag": "ai"})
    assert any("compendium://" in t.uri_template for t in templates)
    assert "Clarity beats cleverness" in res.contents[0].text
    assert "Chunk size" in nested.contents[0].text
    assert "source='notes'" in got.messages[0].content.text
