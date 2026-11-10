import pytest

from compendium_mcp.core import SourceError
from compendium_mcp.query import terms


def test_rows_are_items(sources):
    books = sources["books"]
    items = books.list()
    assert len(items) == 4
    assert items[0].id == "books.csv#1"
    assert {i.title for i in items} >= {"The Pragmatic Programmer", "Co-Intelligence"}


def test_read_row(sources):
    text = sources["books"].read("books.csv#3")
    assert "title: Co-Intelligence" in text and "author: Ethan Mollick" in text


def test_search_rows(sources):
    hit = sources["books"].search(terms("replication consistency"), 5)[0]
    assert hit.title == "Designing Data-Intensive Applications"
    assert hit.id == "books.csv#1"


def test_bad_row_ids(sources):
    books = sources["books"]
    for bad in ["books.csv", "books.csv#abc", "books.csv#0", "books.csv#99", "other.csv#1"]:
        with pytest.raises(SourceError):
            books.read(bad)


def test_folder_of_csvs(tmp_path):
    from compendium_mcp.sources.csvsource import CsvSource

    (tmp_path / "a.csv").write_text("name,city\nAda,London\n")
    (tmp_path / "b.csv").write_text("name,city\nGrace,Arlington\n")
    src = CsvSource("people", tmp_path)
    assert {i.id for i in src.list()} == {"a.csv#1", "b.csv#1"}
    assert src.search(terms("arlington"), 5)[0].id == "b.csv#1"
