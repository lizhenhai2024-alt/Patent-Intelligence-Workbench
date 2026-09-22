"""Download provider contracts and result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.patent_number import PatentNumber


class DownloadError(RuntimeError):
    """Base error for PDF download failures."""


class DownloadValidationError(DownloadError):
    """Raised when downloaded bytes are not a valid PDF payload."""


@dataclass(frozen=True, slots=True)
class OfficialSourceHint:
    name: str
    url: str
    access_mode: str
    document_type: str
    note: str | None = None


class DownloadExhaustedError(DownloadError):
    """All automated providers failed; structured official fallbacks remain."""

    def __init__(
        self,
        publication_number: str,
        attempts: tuple[DownloadAttempt, ...],
        official_sources: tuple[OfficialSourceHint, ...] = (),
    ) -> None:
        self.publication_number = publication_number
        self.attempts = attempts
        self.official_sources = official_sources
        self.all_unsupported = all(
            not attempt.attempted for attempt in attempts
        )
        details = "; ".join(
            f"{attempt.provider}: {attempt.error or 'failed'}"
            for attempt in attempts
        )
        hint_text = ""
        if official_sources:
            names = ", ".join(
                f"{hint.name} [{hint.access_mode}]" for hint in official_sources
            )
            hint_text = f" Official alternatives: {names}."
        super().__init__(
            f"No automated PDF provider succeeded for {publication_number}. "
            f"{details}.{hint_text}"
        )


@dataclass(frozen=True, slots=True)
class PdfPayload:
    provider: str
    source_url: str
    data: bytes


@dataclass(frozen=True, slots=True)
class DownloadAttempt:
    provider: str
    attempted: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadResult:
    publication_number: str
    path: Path
    provider: str
    source_url: str | None
    attempts: tuple[DownloadAttempt, ...]
    from_cache: bool = False


class PdfDownloadProvider(Protocol):
    name: str

    def supports(self, publication: PatentNumber) -> bool:
        ...

    async def fetch_pdf(self, publication: PatentNumber) -> PdfPayload:
        ...
