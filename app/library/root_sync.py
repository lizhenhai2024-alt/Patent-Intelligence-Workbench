"""Synchronize a filesystem PatentLibrary root into SQLite."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.company_registry import CompanyRegistry
from app.library.local_patent_index import import_patent_folder
from app.library.store import SQLitePatentLibrary


@dataclass(frozen=True, slots=True)
class RootSyncSummary:
    folders: int
    imported: int
    attached_pdfs: int
    unknown_folders: tuple[str, ...]


def sync_library_root(
    store: SQLitePatentLibrary,
    root: Path,
    registry: CompanyRegistry | None = None,
) -> RootSyncSummary:
    root = Path(root)
    registry = registry or CompanyRegistry.default()
    imported = attached = folders = 0
    unknown: list[str] = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        group_id = None
        assignee = None
        try:
            company = registry.get(folder.name)
            group_id = company.group_id
            assignee = company.display_name
        except KeyError:
            unknown.append(folder.name)
        summary = import_patent_folder(
            store,
            folder,
            company_group=group_id,
            default_assignee=assignee,
        )
        folders += 1
        imported += summary.imported
        attached += summary.attached_pdfs
    return RootSyncSummary(folders, imported, attached, tuple(unknown))
