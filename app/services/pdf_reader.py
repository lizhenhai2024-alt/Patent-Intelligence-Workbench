"""Extract patent Reader sections and drawing pages from local PDF files."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf as fitz

from app.domain.reader import PatentFigure, PatentReaderDocument
from app.providers.epo_ops import EpoImageLayout

_CLAIM_START_RE = re.compile(r"^\s*1[.、]\s*\S", re.MULTILINE)
_DESCRIPTION_MARKERS = (
    "技术领域",
    "背景技术",
    "具体实施方式",
    "FIELD",
    "BACKGROUND",
    "DETAILED DESCRIPTION",
)
_DRAWING_MARKERS = ("说明书附图", "DRAWINGS")


def extract_pdf_reader_document(
    publication_number: str,
    pdf_path: str | Path,
    cache_root: str | Path,
    *,
    layout: EpoImageLayout | None = None,
) -> PatentReaderDocument:
    """Extract text sections and render drawing pages from a patent PDF."""
    path = Path(pdf_path)
    cache = Path(cache_root) / publication_number / "figures"
    doc = fitz.open(path)
    try:
        page_text = tuple(page.get_text("text") for page in doc)
        resolved_layout = layout or _infer_layout(page_text)
        claims = _section_text(doc, resolved_layout, "CLAIMS")
        description = _section_text(doc, resolved_layout, "DESCRIPTION")
        figures = _render_drawings(doc, resolved_layout, cache)
    finally:
        doc.close()

    source = f"PDF · {publication_number}"
    return PatentReaderDocument(
        publication_number=publication_number,
        claims=claims,
        description=description,
        figures=figures,
        claims_source=source if claims else None,
        description_source=source if description else None,
        figures_source=source if figures else None,
    )


def _section_text(
    doc: fitz.Document,
    layout: EpoImageLayout | None,
    section: str,
) -> str:
    if layout is None:
        return ""
    start = layout.start_page(section)
    end = layout.end_page(section)
    if start is None or end is None:
        return ""
    blocks: list[str] = []
    for page_number in range(start, min(end, len(doc)) + 1):
        text = _clean_pdf_text(doc[page_number - 1].get_text("text"))
        if text:
            blocks.append(text)
    return "\n\n".join(blocks)


def _render_drawings(
    doc: fitz.Document,
    layout: EpoImageLayout | None,
    cache: Path,
) -> tuple[PatentFigure, ...]:
    if layout is None:
        return ()
    start = layout.start_page("DRAWINGS")
    end = layout.end_page("DRAWINGS")
    if start is None or end is None:
        return ()

    cache.mkdir(parents=True, exist_ok=True)
    figures: list[PatentFigure] = []
    for page_number in range(start, min(end, len(doc)) + 1):
        image_path = cache / f"page-{page_number:03d}.png"
        if not image_path.exists():
            page = doc[page_number - 1]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            pixmap.save(str(image_path))
        uri = image_path.resolve().as_uri()
        figures.append(PatentFigure(thumbnail_url=uri, full_url=uri))
    return tuple(figures)


def _infer_layout(page_text: tuple[str, ...]) -> EpoImageLayout | None:
    if not page_text:
        return None
    starts: dict[str, int] = {}

    for index, text in enumerate(page_text, start=1):
        compact = " ".join(text.split())
        upper = compact.upper()
        if "DRAWINGS" not in starts and any(
            marker in upper if marker.isascii() else marker in compact
            for marker in _DRAWING_MARKERS
        ):
            starts["DRAWINGS"] = index
        if "DESCRIPTION" not in starts and any(
            marker in upper if marker.isascii() else marker in compact
            for marker in _DESCRIPTION_MARKERS
        ):
            starts["DESCRIPTION"] = index

    description_start = starts.get("DESCRIPTION", len(page_text) + 1)
    for index, text in enumerate(page_text, start=1):
        if index >= description_start:
            break
        compact = _clean_pdf_text(text)
        if _CLAIM_START_RE.search(compact):
            starts["CLAIMS"] = index
            break

    if not starts:
        return None
    return EpoImageLayout(
        total_pages=len(page_text),
        section_starts=tuple(
            sorted(starts.items(), key=lambda item: item[1])
        ),
    )


def _clean_pdf_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()
