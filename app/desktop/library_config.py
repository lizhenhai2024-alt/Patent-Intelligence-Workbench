"""Persistent LocalLibrary filesystem settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LibraryFolderConfig:
    root: Path


@dataclass(frozen=True, slots=True)
class BackfillConfig:
    default_limit: int = 200
    coverage_threshold: float = 0.5
    date_missing_threshold: float = 0.2


def _load_settings(config_path: Path) -> dict:
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save_settings(config_path: Path, data: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_library_folder(config_path: Path, default_root: Path) -> LibraryFolderConfig:
    value = str(_load_settings(config_path).get("library_root") or "").strip()
    if value:
        return LibraryFolderConfig(Path(value))
    return LibraryFolderConfig(default_root)


def save_library_folder(config_path: Path, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    data = _load_settings(config_path)
    data["library_root"] = str(root)
    _save_settings(config_path, data)


def load_backfill_config(config_path: Path) -> BackfillConfig:
    data = _load_settings(config_path).get("backfill") or {}
    return BackfillConfig(
        default_limit=max(1, min(int(data.get("default_limit", 200)), 1000)),
        coverage_threshold=max(0.0, min(float(data.get("coverage_threshold", 0.5)), 1.0)),
        date_missing_threshold=max(0.0, min(float(data.get("date_missing_threshold", 0.2)), 1.0)),
    )


def save_backfill_config(config_path: Path, config: BackfillConfig) -> None:
    data = _load_settings(config_path)
    data["backfill"] = {
        "default_limit": config.default_limit,
        "coverage_threshold": config.coverage_threshold,
        "date_missing_threshold": config.date_missing_threshold,
    }
    _save_settings(config_path, data)
