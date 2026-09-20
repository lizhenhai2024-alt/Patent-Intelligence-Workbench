"""Provider-fallback PDF download manager."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from app.core.patent_number import PatentNumber
from app.downloads.base import (
    DownloadAttempt,
    DownloadError,
    DownloadExhaustedError,
    DownloadResult,
    DownloadValidationError,
    PdfDownloadProvider,
)
from app.downloads.source_catalog import DownloadSourceCatalog


def is_valid_pdf(data: bytes) -> bool:
    return len(data) >= 8 and data.startswith(b"%PDF-")


def is_valid_pdf_file(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 8:
        return False
    with path.open("rb") as stream:
        return stream.read(5) == b"%PDF-"


class DownloadManager:
    def __init__(
        self,
        providers: Iterable[PdfDownloadProvider],
        source_catalog: DownloadSourceCatalog | None = None,
    ):
        self.providers = tuple(providers)
        self.source_catalog = source_catalog

    async def download(
        self,
        publication: PatentNumber,
        destination: str | Path,
        *,
        overwrite: bool = False,
    ) -> DownloadResult:
        destination_path = Path(destination)

        if not overwrite and is_valid_pdf_file(destination_path):
            return DownloadResult(
                publication_number=publication.canonical,
                path=destination_path,
                provider="LOCAL_CACHE",
                source_url=None,
                attempts=(),
                from_cache=True,
            )

        attempts: list[DownloadAttempt] = []
        for provider in self.providers:
            if not provider.supports(publication):
                attempts.append(
                    DownloadAttempt(
                        provider=provider.name,
                        attempted=False,
                        error="unsupported publication",
                    )
                )
                continue

            try:
                payload = await provider.fetch_pdf(publication)
                if not is_valid_pdf(payload.data):
                    raise DownloadValidationError(
                        f"{provider.name} returned a non-PDF payload."
                    )
                _atomic_write(destination_path, payload.data)
            except DownloadError as exc:
                attempts.append(
                    DownloadAttempt(
                        provider=provider.name,
                        attempted=True,
                        error=str(exc),
                    )
                )
                continue

            attempts.append(
                DownloadAttempt(
                    provider=provider.name,
                    attempted=True,
                )
            )
            return DownloadResult(
                publication_number=publication.canonical,
                path=destination_path,
                provider=payload.provider,
                source_url=payload.source_url,
                attempts=tuple(attempts),
            )

        official_sources = (
            self.source_catalog.hints_for(publication)
            if self.source_catalog is not None
            else ()
        )
        raise DownloadExhaustedError(
            publication_number=publication.canonical,
            attempts=tuple(attempts),
            official_sources=official_sources,
        )


def _atomic_write(destination: Path, data: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        temporary.write_bytes(data)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
