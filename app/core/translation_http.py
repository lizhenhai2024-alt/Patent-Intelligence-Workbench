"""HTTP translation provider with simple JSON API support."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.translation import TranslationProvider, TranslationResult


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
    provider: TranslationProvider
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


_DEEPL_LANGUAGE_OVERRIDES = {
    "zh-cn": "ZH",
    "zh": "ZH",
    "zh-hans": "ZH",
    "auto": "",
}


def _deepl_language_code(language: str) -> str:
    """Map this app's BCP-47-ish language tags to DeepL's language codes."""
    normalized = language.strip().lower()
    if normalized in _DEEPL_LANGUAGE_OVERRIDES:
        return _DEEPL_LANGUAGE_OVERRIDES[normalized]
    return normalized.split("-")[0].upper()


@dataclass(slots=True)
class DeepLTranslationProvider:
    """DeepL API v2 translation provider (JA/KO/DE full-text patent translation)."""

    api_key: str
    endpoint: str = "https://api-free.deepl.com/v2/translate"
    timeout_seconds: float = 30.0
    name: str = "DEEPL"

    def translate(
        self,
        text: str,
        *,
        source_language: str = "auto",
        target_language: str = "zh-CN",
    ) -> TranslationResult:
        payload: dict[str, object] = {
            "text": [text],
            "target_lang": _deepl_language_code(target_language) or "ZH",
        }
        source_code = _deepl_language_code(source_language)
        if source_code:
            payload["source_lang"] = source_code
        response = httpx.post(
            self.endpoint,
            json=payload,
            headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        translations = data.get("translations")
        if not isinstance(translations, list) or not translations:
            raise RuntimeError("DeepL 未返回翻译结果。")
        translated = translations[0].get("text")
        if not isinstance(translated, str):
            raise RuntimeError("DeepL 翻译服务返回格式无法识别。")
        return TranslationResult(
            text=translated,
            provider=self.name,
            source_language=source_language,
            target_language=target_language,
        )


_LLM_TARGET_LANGUAGE_LABELS = {
    "zh-cn": "中文",
    "zh": "中文",
    "zh-hans": "中文",
    "en": "英文",
    "ja": "日文",
    "ko": "韩文",
    "de": "德文",
}


def _llm_target_language_label(language: str) -> str:
    """Map this app's language tags to a human label for the translation prompt."""
    normalized = language.strip().lower()
    return _LLM_TARGET_LANGUAGE_LABELS.get(normalized, language.strip() or "中文")


@dataclass(slots=True)
class LlmTranslationProvider:
    """Translation via an OpenAI-compatible Chat Completions endpoint.

    Covers any mainstream AI API that speaks this contract: OpenAI, DeepSeek,
    Qwen (DashScope compatible mode), Zhipu GLM, Moonshot Kimi, Doubao/Ark,
    Xiaomi MiMo, and self-hosted OpenAI-compatible gateways.
    """

    endpoint: str
    api_key: str
    model: str
    timeout_seconds: float = 45.0
    name: str = "LLM_TRANSLATE"

    def translate(
        self,
        text: str,
        *,
        source_language: str = "auto",
        target_language: str = "zh-CN",
    ) -> TranslationResult:
        label = _llm_target_language_label(target_language)
        prompt = (
            f"将下面的专利文本准确翻译成{label}，保留技术术语、编号和单位，"
            f"只输出译文本身，不要添加解释或引号：\n\n{text}"
        )
        payload = {
            "model": self.model.strip(),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        response = httpx.post(
            self.endpoint,
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key.strip()}"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("AI 翻译服务返回格式无法识别。") from exc
        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("AI 翻译服务未返回可用译文。")
        return TranslationResult(
            text=content.strip(),
            provider=self.name,
            source_language=source_language,
            target_language=target_language,
        )
