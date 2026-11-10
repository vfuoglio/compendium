import shutil
from pathlib import Path

import pytest

from compendium_mcp.config import load_config
from compendium_mcp.hub import Hub

EXAMPLE = Path(__file__).parent.parent / "example"


@pytest.fixture
def example_dir(tmp_path):
    dest = tmp_path / "example"
    shutil.copytree(EXAMPLE, dest)
    return dest


@pytest.fixture
def sources(example_dir):
    return load_config(example_dir / "compendium.toml")


@pytest.fixture
def hub(sources):
    return Hub(sources)


def minimal_pdf(text: str) -> bytes:
    """A tiny single-page PDF with one line of text, built by hand."""
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET"
    objs[3] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out
