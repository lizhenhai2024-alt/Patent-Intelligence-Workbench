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
