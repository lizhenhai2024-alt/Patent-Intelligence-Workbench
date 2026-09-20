"""CSV and Excel exports for local patent library views."""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.library.models import LibraryPatent

EXPORT_COLUMNS = (
    "publication_number",
    "jurisdiction",
    "kind_code",
    "family_key",
    "family_type",
    "source_family_id",
    "title",
    "application_number",
    "grant_number",
    "publication_date",
    "earliest_priority_number",
    "earliest_priority_date",
    "original_assignees",
    "current_assignees",
    "company_groups",
    "technology_topics",
    "projects",
    "tags",
    "pdf_paths",
    "watch_rule_ids",
    "favorite",
    "note",
    "first_seen_at",
    "last_seen_at",
    "source",
)


def patent_to_export_row(patent: LibraryPatent) -> dict[str, str | bool]:
    return {
        "publication_number": patent.publication_number,
        "jurisdiction": patent.jurisdiction,
        "kind_code": patent.kind_code or "",
        "family_key": patent.family_key or "",
        "family_type": patent.family_type or "",
        "source_family_id": patent.source_family_id or "",
        "title": patent.title or "",
        "application_number": patent.application_number or "",
        "grant_number": patent.grant_number or "",
        "publication_date": patent.publication_date.isoformat()
        if patent.publication_date
        else "",
        "earliest_priority_number": patent.earliest_priority_number or "",
        "earliest_priority_date": patent.earliest_priority_date.isoformat()
        if patent.earliest_priority_date
        else "",
        "original_assignees": " | ".join(patent.original_assignees),
        "current_assignees": " | ".join(patent.current_assignees),
        "company_groups": " | ".join(patent.company_groups),
        "technology_topics": " | ".join(patent.technology_topics),
        "projects": " | ".join(patent.projects),
        "tags": " | ".join(patent.tags),
        "pdf_paths": " | ".join(str(path) for path in patent.pdf_paths),
        "watch_rule_ids": " | ".join(patent.watch_rule_ids),
        "favorite": patent.favorite,
        "note": patent.note or "",
        "first_seen_at": patent.first_seen_at.isoformat(),
        "last_seen_at": patent.last_seen_at.isoformat(),
        "source": patent.source or "",
    }


def export_csv(
    patents: tuple[LibraryPatent, ...],
    destination: str | Path,
) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for patent in patents:
            writer.writerow(patent_to_export_row(patent))
    return path


def export_xlsx(
    patents: tuple[LibraryPatent, ...],
    destination: str | Path,
) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Patent Library"

    for column_index, name in enumerate(EXPORT_COLUMNS, start=1):
        cell = sheet.cell(row=1, column=column_index, value=name)
        cell.font = Font(bold=True)

    for row_index, patent in enumerate(patents, start=2):
        values = patent_to_export_row(patent)
        for column_index, name in enumerate(EXPORT_COLUMNS, start=1):
            sheet.cell(
                row=row_index,
                column=column_index,
                value=values[name],
            )

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    for column_index, name in enumerate(EXPORT_COLUMNS, start=1):
        values = [name]
        for patent in patents[:200]:
            values.append(str(patent_to_export_row(patent)[name]))
        max_length = min(max((len(value) for value in values), default=10) + 2, 60)
        sheet.column_dimensions[get_column_letter(column_index)].width = max_length

    workbook.save(path)
    return path
