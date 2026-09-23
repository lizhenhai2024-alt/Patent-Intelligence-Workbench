"""Resilient multi-source Patent Reader orchestration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pymupdf as fitz

from app.core.patent_number import PatentNumber, PatentNumberError, normalize_patent_number
from app.domain.family import FamilyType
from app.domain.reader import PatentFigure, PatentReaderDocument
from app.downloads.base import DownloadError
from app.downloads.manager import DownloadManager, is_valid_pdf_file
from app.library.store import SQLitePatentLibrary
from app.providers.base import ProviderError
from app.providers.epo_ops import EpoImageLayout, EpoOpsProvider
from app.providers.google_patents_search import GooglePatentsSearchProvider
from app.services.family_resolver import FamilyResolver
from app.services.pdf_reader import extract_pdf_reader_document

_EPO_FULLTEXT_AUTHORITIES = {
    "EP",
    "WO",
    "AT",
    "BE",
    "BG",
    "CA",
    "CH",
    "CY",
    "CZ",
    "DK",
    "EE",
    "ES",
    "FR",
    "GB",
    "GR",
    "HR",
    "IE",
    "IT",
    "LT",
    "LU",
    "MC",
    "MD",
    "ME",
    "NO",
    "PL",
    "PT",
    "RO",
    "RS",
    "SE",
    "SK",
}


class ReaderService:
    def __init__(
        self,
        *,
        library_store: SQLitePatentLibrary,
        family_resolver: FamilyResolver,
        download_manager: DownloadManager,
        cache_root: str | Path,
        google_provider: GooglePatentsSearchProvider | None = None,
        epo_provider: EpoOpsProvider | None = None,
    ) -> None:
        self.library_store = library_store
        self.family_resolver = family_resolver
        self.download_manager = download_manager
        self.cache_root = Path(cache_root)
        self.google_provider = google_provider or GooglePatentsSearchProvider(max_attempts=1)
        self.epo_provider = epo_provider

    async def load(
        self,
        publication: PatentNumber,
        *,
        seed: PatentReaderDocument | None = None,
    ) -> PatentReaderDocument:
        document = seed or PatentReaderDocument(publication_number=publication.canonical)
        warnings: list[str] = list(document.warnings)

        try:
            google_document = await self.google_provider.get_reader_document(publication)
        except ProviderError as exc:
            warnings.append(f"Google Patents Reader unavailable: {exc}")
        else:
            document = _merge_document(
                document,
                replace(
                    google_document,
                    claims_source="Google Patents" if google_document.claims else None,
                    description_source=(
                        "Google Patents" if google_document.description else None
                    ),
                    figures_source="Google Patents" if google_document.figures else None,
                ),
            )

        layout = await self._image_layout(publication, warnings)

        if _needs_local_pdf(document):
            pdf_path = await self._resolve_pdf(publication, warnings)
            if pdf_path is not None:
                try:
                    pdf_document = extract_pdf_reader_document(
                        publication.canonical,
                        pdf_path,
                        self.cache_root,
                        layout=layout,
                    )
                except Exception as exc:
                    warnings.append(f"PDF Reader fallback failed: {exc}")
                else:
                    document = _merge_document(document, pdf_document)

        if (
            self.epo_provider is not None
            and publication.jurisdiction.upper() in _EPO_FULLTEXT_AUTHORITIES
            and (not document.claims or not document.description)
        ):
            document = await self._merge_epo_fulltext(
                document,
                publication,
                warnings,
                source_label=f"EPO OPS · {publication.canonical}",
            )

        if self.epo_provider is not None and (
            not document.claims or not document.description
        ):
            document = await self._merge_family_fulltext(
                document,
                publication,
                warnings,
            )

        if (
            not document.figures
            and self.epo_provider is not None
            and layout is not None
        ):
            try:
                figures = await self._render_epo_drawings(publication, layout)
            except ProviderError as exc:
                warnings.append(f"EPO drawing fallback failed: {exc}")
            except Exception as exc:
                warnings.append(f"EPO drawing render failed: {exc}")
            else:
                if figures:
                    document = replace(
                        document,
                        figures=figures,
                        figures_source=f"EPO OPS images · {publication.canonical}",
                    )

        return replace(document, warnings=tuple(dict.fromkeys(warnings)))

    async def _image_layout(
        self,
        publication: PatentNumber,
        warnings: list[str],
    ) -> EpoImageLayout | None:
        if self.epo_provider is None:
            return None
        try:
            return await self.epo_provider.get_image_layout(publication)
        except ProviderError as exc:
            warnings.append(f"EPO image layout unavailable: {exc}")
            return None

    async def _resolve_pdf(
        self,
        publication: PatentNumber,
        warnings: list[str],
    ) -> Path | None:
        patent = self.library_store.get_patent(publication.canonical)
        if patent is not None:
            for document in patent.documents:
                path = Path(document.path)
                if is_valid_pdf_file(path):
                    return path

        destination = self.cache_root / publication.canonical / f"{publication.canonical}.pdf"
        try:
            result = await self.download_manager.download(publication, destination)
        except DownloadError as exc:
            warnings.append(f"PDF download fallback unavailable: {exc}")
            return None
        return result.path

    async def _merge_epo_fulltext(
        self,
        document: PatentReaderDocument,
        publication: PatentNumber,
        warnings: list[str],
        *,
        source_label: str,
    ) -> PatentReaderDocument:
        assert self.epo_provider is not None
        claims = ""
        description = ""
        try:
            if not document.claims:
                claims = await self.epo_provider.get_fulltext_section(
                    publication,
                    "claims",
                )
            if not document.description:
                description = await self.epo_provider.get_fulltext_section(
                    publication,
                    "description",
                )
        except ProviderError as exc:
            warnings.append(f"{source_label} full text unavailable: {exc}")
            return document

        return replace(
            document,
            claims=document.claims or claims,
            description=document.description or description,
            claims_source=(
                document.claims_source
                or (source_label if claims else None)
            ),
            description_source=(
                document.description_source
                or (source_label if description else None)
            ),
        )

    async def _merge_family_fulltext(
        self,
        document: PatentReaderDocument,
        publication: PatentNumber,
        warnings: list[str],
    ) -> PatentReaderDocument:
        try:
            resolution = await self.family_resolver.resolve(
                publication,
                FamilyType.DOCDB_SIMPLE,
            )
        except ProviderError as exc:
            warnings.append(f"Family full-text fallback unavailable: {exc}")
            return document

        candidates = sorted(
            (
                member
                for member in resolution.family.members
                if member.publication_number != publication.canonical
                and member.jurisdiction.upper() in _EPO_FULLTEXT_AUTHORITIES
            ),
            key=lambda member: (
                0 if member.jurisdiction.upper() == "EP" else 1,
                0 if member.jurisdiction.upper() == "WO" else 1,
                member.publication_number,
            ),
        )
        for member in candidates:
            try:
                candidate = normalize_patent_number(member.publication_number)
            except PatentNumberError:
                continue
            before = (bool(document.claims), bool(document.description))
            source = f"EPO OPS · 同族 {candidate.canonical}"
            document = await self._merge_epo_fulltext(
                document,
                candidate,
                warnings,
                source_label=source,
            )
            after = (bool(document.claims), bool(document.description))
            if after == (True, True) or after != before:
                if after == (True, True):
                    break
        return document

    async def _render_epo_drawings(
        self,
        publication: PatentNumber,
        layout: EpoImageLayout,
    ) -> tuple[PatentFigure, ...]:
        assert self.epo_provider is not None
        start = layout.start_page("DRAWINGS")
        end = layout.end_page("DRAWINGS")
        if start is None or end is None:
            return ()

        folder = self.cache_root / publication.canonical / "figures"
        folder.mkdir(parents=True, exist_ok=True)
        figures: list[PatentFigure] = []
        for page in range(start, end + 1):
            image_path = folder / f"epo-page-{page:03d}.png"
            if not image_path.exists():
                data = await self.epo_provider.get_image_page_pdf(publication, page)
                if not data:
                    continue
                _render_single_pdf_page(data, image_path)
            uri = image_path.resolve().as_uri()
            figures.append(PatentFigure(thumbnail_url=uri, full_url=uri))
        return tuple(figures)


def _merge_document(
    base: PatentReaderDocument,
    extra: PatentReaderDocument,
) -> PatentReaderDocument:
    return PatentReaderDocument(
        publication_number=base.publication_number or extra.publication_number,
        title=base.title or extra.title,
        abstract=base.abstract or extra.abstract,
        claims=base.claims or extra.claims,
        description=base.description or extra.description,
        classifications=base.classifications or extra.classifications,
        figures=base.figures or extra.figures,
        claims_source=base.claims_source or extra.claims_source,
        description_source=base.description_source or extra.description_source,
        figures_source=base.figures_source or extra.figures_source,
        warnings=tuple(dict.fromkeys((*base.warnings, *extra.warnings))),
    )


def _needs_local_pdf(document: PatentReaderDocument) -> bool:
    return not document.claims or not document.description or not document.figures


def _render_single_pdf_page(data: bytes, destination: Path) -> None:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if not doc:
            return
        pixmap = doc[0].get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
        pixmap.save(str(destination))
    finally:
        doc.close()
