import pytest
from conftest import minimal_pdf

from compendium_mcp.core import SourceError
from compendium_mcp.query import terms
from compendium_mcp.sources.files import FilesSource


def test_txt_list_read_search(sources):
    docs = sources["docs"]
    assert [i.kind for i in docs.list()] == ["txt"]
    assert "hosting migration" in docs.read("meeting-2026-11-03.txt")
    hit = docs.search(terms("vendor contract renewal"), 5)[0]
    assert hit.id == "meeting-2026-11-03.txt" and "contract" in hit.snippet.lower()


def test_never_writable(sources):
    assert not sources["docs"].writable
    with pytest.raises(SourceError):
        sources["docs"].create("x.txt", "x")


def test_pdf_and_docx(tmp_path):
    import docx

    (tmp_path / "paper.pdf").write_bytes(minimal_pdf("Quantum widgets are fascinating"))
    d = docx.Document()
    d.add_paragraph("Quarterly budget review for the platform team")
    d.save(tmp_path / "budget.docx")

    src = FilesSource("docs", tmp_path)
    assert {i.id for i in src.list()} == {"paper.pdf", "budget.docx"}
    assert "Quantum widgets" in src.read("paper.pdf")
    assert src.search(terms("quarterly budget"), 5)[0].id == "budget.docx"
    assert src.search(terms("quantum"), 5)[0].id == "paper.pdf"


def test_corrupt_pdf_does_not_break_search(tmp_path):
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    (tmp_path / "ok.txt").write_text("hello needle world")
    assert [h.id for h in FilesSource("d", tmp_path).search(terms("needle"), 5)] == ["ok.txt"]


def test_unsupported_and_traversal(sources):
    for bad in ["../x.txt", "a.exe", "/etc/passwd.txt"]:
        with pytest.raises(SourceError):
            sources["docs"].read(bad)
