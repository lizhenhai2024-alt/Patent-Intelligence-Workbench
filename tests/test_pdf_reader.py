from pathlib import Path

import pymupdf as fitz

from app.providers.epo_ops import EpoImageLayout
from app.services.pdf_reader import extract_pdf_reader_document


def test_pdf_import_does_not_pollute_stdout():
    """fitz deprecation warnings on stdout break MCP JSON-RPC framing."""
    import contextlib
    import importlib
    import io
    import sys

    for name in list(sys.modules):
        if name in {"app.services.pdf_reader", "app.services.reader_service"} or name.startswith(
            "fitz"
        ):
            sys.modules.pop(name, None)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        importlib.import_module("app.services.pdf_reader")
    assert buffer.getvalue() == ""


def _write_test_pdf(path: Path) -> None:
    doc = fitz.open()
    pages = (
        "Bibliography and abstract",
        "1. A damper comprising a pressure tube.\n2. The damper of claim 1.",
        "FIELD\n[0001] The disclosure relates to suspension dampers.",
        "Figure 1",
        "Figure 2",
    )
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_pdf_reader_extracts_sections_and_renders_drawings(tmp_path):
    pdf = tmp_path / "CN123A.pdf"
    _write_test_pdf(pdf)
    layout = EpoImageLayout(
        total_pages=5,
        section_starts=(
            ("BIBLIOGRAPHY", 1),
            ("CLAIMS", 2),
            ("DESCRIPTION", 3),
            ("DRAWINGS", 4),
        ),
    )

    document = extract_pdf_reader_document(
        "CN123A",
        pdf,
        tmp_path / "cache",
        layout=layout,
    )

    assert "1. A damper" in document.claims
    assert "[0001] The disclosure" in document.description
    assert len(document.figures) == 2
    assert document.claims_source == "PDF · CN123A"
    assert document.description_source == "PDF · CN123A"
    assert document.figures_source == "PDF · CN123A"
    for figure in document.figures:
        assert figure.full_url.startswith("file:")
