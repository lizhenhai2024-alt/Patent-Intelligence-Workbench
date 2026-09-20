"""High-level operations for the local patent library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.library.export import export_csv, export_xlsx
from app.library.models import LibraryPatent, LibraryQuery
from app.library.store import SQLitePatentLibrary


@dataclass(slots=True)
class PatentLibraryService:
    store: SQLitePatentLibrary

    def search(self, query: LibraryQuery | None = None) -> tuple[LibraryPatent, ...]:
        return self.store.query(query)

    def export(
        self,
        destination: str | Path,
        *,
        query: LibraryQuery | None = None,
    ) -> Path:
        patents = self.store.query(query)
        path = Path(destination)
        suffix = path.suffix.casefold()
        if suffix == ".csv":
            return export_csv(patents, path)
        if suffix == ".xlsx":
            return export_xlsx(patents, path)
        raise ValueError("Export destination must end in .csv or .xlsx")
