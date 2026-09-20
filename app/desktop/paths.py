"""Cross-platform user-data locations for the desktop application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "PatentIntelligenceWorkbench"
UNIFIED_DB_NAME = "workbench.db"
LEGACY_LIBRARY_DB_NAME = "patent_library.db"
LEGACY_WATCH_DB_NAME = "patent_watch.db"


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    library_db: Path
    watch_db: Path
    downloads: Path
    exports: Path

    @classmethod
    def for_root(cls, root: str | Path) -> AppPaths:
        resolved = Path(root).expanduser()
        library_db, watch_db = _database_paths(resolved)
        return cls(
            root=resolved,
            library_db=library_db,
            watch_db=watch_db,
            downloads=resolved / "downloads",
            exports=resolved / "exports",
        )

    @classmethod
    def default(cls) -> AppPaths:
        override = os.getenv("PIW_DATA_DIR")
        if override:
            root = Path(override).expanduser()
        elif os.name == "nt":
            base = os.getenv("LOCALAPPDATA")
            root = (
                Path(base) / APP_DIR_NAME
                if base
                else Path.home() / "AppData" / "Local" / APP_DIR_NAME
            )
        else:
            root = Path.home() / ".local" / "share" / APP_DIR_NAME

        return cls.for_root(root)

    @property
    def uses_unified_database(self) -> bool:
        return self.library_db == self.watch_db

    def ensure(self) -> AppPaths:
        self.root.mkdir(parents=True, exist_ok=True)
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.exports.mkdir(parents=True, exist_ok=True)
        return self


def _database_paths(root: Path) -> tuple[Path, Path]:
    unified = root / UNIFIED_DB_NAME
    legacy_library = root / LEGACY_LIBRARY_DB_NAME
    legacy_watch = root / LEGACY_WATCH_DB_NAME

    if unified.exists():
        return unified, unified

    # Existing development/user data is kept on its legacy paths to avoid
    # silent data loss. Fresh installations use one database for all local
    # library and watch tables.
    if legacy_library.exists() or legacy_watch.exists():
        return legacy_library, legacy_watch

    return unified, unified
