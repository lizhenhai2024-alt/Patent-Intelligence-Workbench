"""Filesystem archiving rules for LocalLibrary patent PDFs."""

from __future__ import annotations

import re
from pathlib import Path

_INVALID = re.compile(r'[<>:"/\\|?*]+')


def safe_folder_name(value: str) -> str:
    cleaned = _INVALID.sub("_", value).strip(" ._")
    return cleaned or "待归类"


def company_folder(root: Path, company_name: str | None) -> Path:
    folder = root / safe_folder_name(company_name or "待归类")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def patent_archive_path(
    root: Path,
    company_name: str | None,
    publication_number: str,
    title: str | None = None,
) -> Path:
    folder = company_folder(root, company_name)
    filename = publication_number
    if title:
        filename += "_" + safe_folder_name(title)[:100]
    return folder / f"{filename}.pdf"
