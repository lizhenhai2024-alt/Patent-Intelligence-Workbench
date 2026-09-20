"""Cross-platform user-data locations for the desktop application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "PatentIntelligenceWorkbench"


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    library_db: Path
    watch_db: Path
    downloads: Path
    exports: Path

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

        return cls(
            root=root,
            library_db=root / "patent_library.db",
            watch_db=root / "patent_watch.db",
            downloads=root / "downloads",
            exports=root / "exports",
        )

    def ensure(self) -> AppPaths:
        self.root.mkdir(parents=True, exist_ok=True)
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.exports.mkdir(parents=True, exist_ok=True)
        return self
