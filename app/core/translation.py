"""Translation abstractions for the patent reader."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TranslationResult:
    text: str
    provider: str
    source_language: str = "auto"
    target_language: str = "zh-CN"


class TranslationProvider(Protocol):
    name: str

    def translate(
        self,
        text: str,
        *,
        source_language: str = "auto",
        target_language: str = "zh-CN",
    ) -> TranslationResult: ...

class UnconfiguredTranslationProvider:
    name = "UNCONFIGURED"

    def translate(
        self,
        text: str,
        *,
        source_language: str = "auto",
        target_language: str = "zh-CN",
    ) -> TranslationResult:
        if not text.strip():
            return TranslationResult(
                text="",
                provider=self.name,
                source_language=source_language,
                target_language=target_language,
            )
        raise RuntimeError("翻译服务尚未配置。请在后续 Settings 中配置翻译 Provider。")
