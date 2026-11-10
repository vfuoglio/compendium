import pytest

from compendium_mcp.core import SourceError
from compendium_mcp.query import terms
from compendium_mcp.sources.markdown import MarkdownSource, parse_tags, parse_title


@pytest.fixture
def md(example_dir):
    return MarkdownSource("notes", example_dir / "notes", read_only=False)


def test_parse_tags_frontmatter_and_inline():
    text = "---\ntags: [A, b]\n---\n# T\nbody #c and #d/e\n```\n#notatag\n```"
    assert parse_tags(text) == ["a", "b", "c", "d/e"]


def test_parse_title():
    assert parse_title("---\ntags: [x]\n---\n# Hello\n", "fb") == "Hello"
    assert parse_title("no heading", "fb") == "fb"


def test_list_and_filters(md):
    ids = {i.id for i in md.list()}
    assert ids == {
        "projects/website-redesign.md", "projects/rag-experiments.md",
        "Design Principles.md", "daily/2026-11-09.md",
    }
    assert {i.id for i in md.list(tag="#design")} == {
        "projects/website-redesign.md", "Design Principles.md",
    }
    assert len(md.list(folder="projects")) == 2


def test_search_ranks_title_matches_first(md):
    hits = md.search(terms("website redesign"), 10)
    assert hits[0].id == "projects/website-redesign.md" and hits[0].snippet


def test_search_multiword_prefers_fuller_match(md):
    assert md.search(terms("rag reranker hybrid"), 10)[0].id == "projects/rag-experiments.md"


def test_backlinks_by_title(md):
    assert {i.id for i in md.links("Design Principles.md")} == {
        "projects/website-redesign.md", "projects/rag-experiments.md",
    }


@pytest.mark.parametrize(
    "bad", ["../secret.md", "/etc/passwd.md", "projects/../../x.md", "n.txt", ".hidden/a.md", ""]
)
def test_path_safety(md, bad):
    with pytest.raises(SourceError):
        md.read(bad)


def test_symlink_escape_blocked(md, example_dir, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("secret")
    (example_dir / "notes" / "link.md").symlink_to(outside)
    with pytest.raises(SourceError):
        md.read("link.md")
    assert "link.md" not in {i.id for i in md.list()}  # also hidden from listings


def test_create_and_append(md):
    assert md.create("inbox/idea.md", "# Idea") == "inbox/idea.md"
    md.append("inbox/idea.md", "more text")
    assert md.read("inbox/idea.md") == "# Idea\n\nmore text\n"
    with pytest.raises(SourceError):
        md.create("inbox/idea.md", "overwrite?")
    assert md.read("inbox/idea.md").startswith("# Idea")


def test_read_only_is_the_default(example_dir):
    ro = MarkdownSource("notes", example_dir / "notes")
    assert not ro.writable
    with pytest.raises(SourceError, match="read-only"):
        ro.create("x.md", "x")
    with pytest.raises(SourceError, match="read-only"):
        ro.append("Design Principles.md", "x")
    assert ro.read("Design Principles.md")


def test_missing_folder(tmp_path):
    with pytest.raises(SourceError):
        MarkdownSource("n", tmp_path / "nope")
