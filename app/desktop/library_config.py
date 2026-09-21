"""Persistent LocalLibrary filesystem settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LibraryFolderConfig:
    root: Path


def load_library_folder(config_path: Path, default_root: Path) -> LibraryFolderConfig:
    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            value = str(payload.get("library_root") or "").strip()
            if value:
                return LibraryFolderConfig(Path(value))
        except (OSError, json.JSONDecodeError):
            pass
    return LibraryFolderConfig(default_root)


def save_library_folder(config_path: Path, root: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"library_root": str(root)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
