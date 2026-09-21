"""Persistent desktop translation settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TranslationSettings:
    endpoint: str
    api_key: str = ""


def load_translation_settings(path: Path) -> TranslationSettings | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    endpoint = str(data.get("endpoint") or "").strip()
    if not endpoint:
        return None
    return TranslationSettings(
        endpoint=endpoint,
        api_key=str(data.get("api_key") or ""),
    )


def save_translation_settings(path: Path, settings: TranslationSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"endpoint": settings.endpoint, "api_key": settings.api_key},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def delete_translation_settings(path: Path) -> None:
    if path.exists():
        path.unlink()
