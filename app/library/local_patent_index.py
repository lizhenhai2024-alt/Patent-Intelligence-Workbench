"""Import a filesystem patent collection into the local SQLite library."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.domain.family import PatentPublication
from app.library.store import SQLitePatentLibrary

_PATENT_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{2}\d{6,}[A-Z]\d?)(?![A-Z0-9])", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class LocalPatentImportSummary:
    imported: int
    attached_pdfs: int
    skipped: int


def _parse_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _pdf_number(path: Path) -> str | None:
    match = _PATENT_RE.search(path.stem.upper())
    return match.group(1) if match else None


def import_patent_folder(
    store: SQLitePatentLibrary,
    folder: Path,
    *,
    company_group: str | None = None,
    default_assignee: str | None = None,
) -> LocalPatentImportSummary:
    folder = Path(folder)
    csv_path = folder / "patent_list_complete.csv"
    rows: dict[str, dict[str, str]] = {}
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                number = (row.get("公开号") or "").strip().upper()
                if number:
                    rows[number] = row

    pdfs = {number: path for path in folder.glob("*.pdf") if (number := _pdf_number(path))}
    imported = attached = skipped = 0
    for number in sorted(set(rows) | set(pdfs)):
        row = rows.get(number, {})
        jurisdiction = number[:2]
        path = pdfs.get(number)
        title = (row.get("专利名称") or "").strip() or None
        if title is None and path is not None:
            stem = path.stem
            title = re.sub(
                rf"^(?:\d{{4}}-)?{re.escape(number)}[-_ ]*",
                "",
                stem,
                flags=re.IGNORECASE,
            ).strip(" _-") or None
        assignee = (row.get("申请人") or "").strip() or default_assignee
        publication = PatentPublication(
            publication_number=number,
            jurisdiction=jurisdiction,
            title=title,
            filing_date=_parse_date(row.get("申请日") or ""),
            publication_date=_parse_date(row.get("公开日") or ""),
            original_assignees=(assignee,) if assignee else (),
        )
        store.upsert_publication(publication, source="LOCAL_PATENT_FOLDER")
        imported += 1
        if company_group:
            store.add_company_group(number, company_group)
        path = pdfs.get(number)
        if path is not None:
            store.attach_pdf(number, path, provider="LOCAL_PATENT_FOLDER")
            attached += 1
    return LocalPatentImportSummary(imported=imported, attached_pdfs=attached, skipped=skipped)
