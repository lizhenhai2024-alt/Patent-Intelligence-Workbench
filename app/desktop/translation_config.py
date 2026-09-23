"""Persistent desktop translation settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TranslationSettings:
    endpoint: str
    api_key: str = ""
    provider: str = "http"
    model: str = ""
    # provider == "llm_profile": translate with a shared AI model profile (key in the
    # profile's secret store, never in translation.json).
    model_profile: str = ""
    # Baidu APPID / Youdao 应用ID / Azure 区域 (not secret; the key lives in the secret store)
    app_id: str = ""


def load_translation_settings(path: Path) -> TranslationSettings | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    endpoint = str(data.get("endpoint") or "").strip()
    provider = str(data.get("provider") or "http")
    model_profile = str(data.get("model_profile") or "").strip()
    if provider == "llm_profile":
        if not model_profile:
            return None
    elif not endpoint:
        return None
    return TranslationSettings(
        endpoint=endpoint,
        api_key=str(data.get("api_key") or ""),
        provider=provider,
        model=str(data.get("model") or ""),
        model_profile=model_profile,
        app_id=str(data.get("app_id") or ""),
    )


def save_translation_settings(path: Path, settings: TranslationSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "endpoint": settings.endpoint,
                "api_key": settings.api_key,
                "provider": settings.provider,
                "model": settings.model,
                "model_profile": settings.model_profile,
                "app_id": settings.app_id,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def delete_translation_settings(path: Path) -> None:
    if path.exists():
        path.unlink()
