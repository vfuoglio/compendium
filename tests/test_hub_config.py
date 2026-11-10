import pytest

from compendium_mcp.config import build_sources, load_config, sources_from_dirs
from compendium_mcp.core import SourceError
from compendium_mcp.hub import Hub


def test_search_across_sources_tags_each_result(hub):
    refs = {h["ref"] for h in hub.search("ai", limit=20)}
    assert "books:books.csv#3" in refs
    assert "notes:projects/rag-experiments.md" in refs


def test_search_one_source_and_unknown_source(hub):
    assert {h["source"] for h in hub.search("ai", source="books")} == {"books"}
    with pytest.raises(SourceError, match="Unknown source"):
        hub.search("ai", source="nope")


def test_read_by_ref(hub):
    assert "Clarity beats cleverness" in hub.read("notes:Design Principles.md")
    assert "Ethan Mollick" in hub.read("books:books.csv#3")
    with pytest.raises(SourceError, match="source:id"):
        hub.read("Design Principles.md")  # ambiguous: several sources


def test_bare_id_allowed_with_single_source(example_dir):
    hub = Hub(sources_from_dirs([str(example_dir / "notes")]))
    assert "Clarity" in hub.read("Design Principles.md")


def test_links_only_where_supported(hub):
    assert {i["ref"] for i in hub.links("notes:Design Principles.md")} == {
        "notes:projects/website-redesign.md", "notes:projects/rag-experiments.md",
    }
    with pytest.raises(SourceError, match="does not support links"):
        hub.links("books:books.csv#1")


def test_writes_respect_per_source_permissions(hub):
    assert hub.create("notes", "x.md", "# X") == "notes:x.md"
    hub.append("notes:x.md", "more")
    with pytest.raises(SourceError, match="read-only"):
        hub.create("docs", "x.txt", "no")
    assert [d["read_only"] for d in hub.describe()] == [False, True, True]


def test_list_items_merges_and_limits(hub):
    assert len(hub.list_items(limit=3)) == 3
    assert {i["source"] for i in hub.list_items(source="books")} == {"books"}


def test_config_validation(tmp_path):
    base = tmp_path
    (tmp_path / "n").mkdir()
    good = {"sources": {"n": {"type": "markdown", "path": "n"}}}
    assert "n" in build_sources(good, base)

    cases = [
        ({}, "no \\[sources"),
        ({"sources": {"Bad Name": {"type": "markdown", "path": "n"}}}, "Invalid source name"),
        ({"sources": {"n": {"path": "n"}}}, "needs a 'type'"),
        ({"sources": {"n": {"type": "nope", "path": "n"}}}, "unknown type"),
        ({"sources": {"n": {"type": "markdown"}}}, "'path' is required"),
        ({"sources": {"n": {"type": "markdown", "path": "n", "raed_only": 1}}}, "unknown option"),
        ({"sources": {"n": {"type": "markdown", "path": "missing"}}}, "does not exist"),
    ]
    for raw, msg in cases:
        with pytest.raises(SourceError, match=msg):
            build_sources(raw, base)


def test_load_config_errors(tmp_path):
    with pytest.raises(SourceError, match="not found"):
        load_config(tmp_path / "nope.toml")
    (tmp_path / "bad.toml").write_text("this is = = not toml")
    with pytest.raises(SourceError, match="Invalid TOML"):
        load_config(tmp_path / "bad.toml")


def test_dir_shortcut_naming_and_read_only(tmp_path):
    (tmp_path / "My Notes").mkdir()
    (tmp_path / "x" / "My Notes").mkdir(parents=True)
    out = sources_from_dirs([str(tmp_path / "My Notes"), str(tmp_path / "x" / "My Notes")])
    assert list(out) == ["my-notes", "my-notes-2"]
    assert not any(s.writable for s in out.values())
    assert all(s.writable for s in sources_from_dirs([str(tmp_path / "My Notes")], True).values())


def test_find_config_explicit_missing_is_an_error(tmp_path, monkeypatch):
    from compendium_mcp.config import find_config

    monkeypatch.delenv("COMPENDIUM_CONFIG", raising=False)
    with pytest.raises(SourceError, match="not found"):
        find_config(str(tmp_path / "nope.toml"))
    monkeypatch.setenv("COMPENDIUM_CONFIG", str(tmp_path / "also-missing.toml"))
    with pytest.raises(SourceError, match="not found"):
        find_config()
    f = tmp_path / "ok.toml"
    f.write_text("")
    assert find_config(str(f)) == f
