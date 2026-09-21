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
    skipped: int = 0
    classified: int = 0
    dry_run: bool = False


def _company_root(root: Path) -> Path:
    patents = root / "10_Patents"
    return patents if patents.is_dir() else root


def sync_library_root(
    store: SQLitePatentLibrary,
    root: Path,
    registry: CompanyRegistry | None = None,
    *,
    dry_run: bool = False,
) -> RootSyncSummary:
    root = _company_root(Path(root))
    registry = registry or CompanyRegistry.default()
    imported = attached = folders = skipped = classified = 0
    unknown: list[str] = []

    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        group_id = None
        try:
            company = registry.get(folder.name)
            group_id = company.group_id
        except KeyError:
            unknown.append(folder.name)

        summary = import_patent_folder(
            store,
            folder,
            company_group=group_id,
            default_assignee=None,
            dry_run=dry_run,
        )
        folders += 1
        imported += summary.imported
        attached += summary.attached_pdfs
        skipped += summary.skipped
        classified += summary.classified

    return RootSyncSummary(
        folders=folders,
        imported=imported,
        attached_pdfs=attached,
        unknown_folders=tuple(unknown),
        skipped=skipped,
        classified=classified,
        dry_run=dry_run,
    )
