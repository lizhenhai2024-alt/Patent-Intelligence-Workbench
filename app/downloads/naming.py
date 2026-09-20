"""Cross-platform paths for patent documents and family folders."""

from __future__ import annotations

import re

_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")


def safe_component(value: str, *, fallback: str = "unknown") -> str:
    cleaned = _INVALID_WINDOWS_CHARS.sub("_", value.strip())
    cleaned = _WHITESPACE.sub(" ", cleaned).strip(" .")
    return cleaned or fallback


def patent_pdf_filename(publication_number: str) -> str:
    return f"{safe_component(publication_number)}.pdf"


def family_folder_name(
    *,
    source_family_id: str | None,
    earliest_priority_number: str | None,
    representative_publication: str | None,
) -> str:
    key = source_family_id or earliest_priority_number or representative_publication or "unknown"
    return f"Family_{safe_component(key)}"
