"""HTTP translation provider with simple JSON API support."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.translation import TranslationResult


@dataclass(slots=True)
class HttpTranslationProvider:
    endpoint: str
    api_key: str | None = None
    timeout_seconds: float = 30.0
    name: str = "HTTP_TRANSLATE"

    def translate(
        self,
        text: str,
        *,
        source_language: str = "auto",
        target_language: str = "zh-CN",
    ) -> TranslationResult:
        payload = {
            "q": text,
            "source": source_language,
            "target": target_language,
            "format": "text",
        }
        if self.api_key:
            payload["api_key"] = self.api_key
        response = httpx.post(
            self.endpoint,
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        translated = data.get("translatedText") or data.get("translation")
        if not isinstance(translated, str):
            raise RuntimeError("翻译服务返回格式无法识别。")
        return TranslationResult(
            text=translated,
            provider=self.name,
            source_language=source_language,
            target_language=target_language,
        )


@dataclass(slots=True)
class CachedTranslationProvider:
    provider: HttpTranslationProvider
    cache_path: Path

    def _cache_key(self, text: str, source_language: str, target_language: str) -> str:
        raw = f"{self.provider.name}|{source_language}|{target_language}|{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def translate(
        self,
        text: str,
        *,
        source_language: str = "auto",
        target_language: str = "zh-CN",
    ) -> TranslationResult:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = {}
        if self.cache_path.exists():
            try:
                cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cache = {}
        key = self._cache_key(text, source_language, target_language)
        cached = cache.get(key)
        if isinstance(cached, str):
            return TranslationResult(
                text=cached,
                provider=f"{self.provider.name}:cache",
                source_language=source_language,
                target_language=target_language,
            )
        result = self.provider.translate(
            text,
            source_language=source_language,
            target_language=target_language,
        )
        cache[key] = result.text
        self.cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result
