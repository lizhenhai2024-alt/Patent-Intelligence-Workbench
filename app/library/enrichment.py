"""Enrich incomplete local-library patent metadata from search providers."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.patent_number import normalize_patent_number
from app.core.technology_classifier import TechnologyClassifier
from app.domain.family import Classification, PatentPublication
from app.library.models import LibraryPatent, LibraryQuery
from app.library.store import SQLitePatentLibrary
from app.providers.base import ProviderError, SearchProvider


@dataclass(frozen=True, slots=True)
class EnrichmentSummary:
    scanned: int
    enriched: int
    failed: int
    unchanged: int


class LibraryEnrichmentService:
    def __init__(
        self,
        store: SQLitePatentLibrary,
        provider: SearchProvider,
        classifier: TechnologyClassifier | None = None,
    ) -> None:
        self.store = store
        self.provider = provider
        self.classifier = classifier or TechnologyClassifier()

    async def enrich_incomplete(self, *, limit: int = 100) -> EnrichmentSummary:
        patents = self.store.query(LibraryQuery(limit=10000))
        candidates = [patent for patent in patents if _needs_enrichment(patent)][:limit]
        scanned = enriched = failed = unchanged = 0
        for patent in candidates:
            scanned += 1
            try:
                changed = await self._enrich_one(patent)
            except (ProviderError, ValueError):
                failed += 1
                continue
            if changed:
                enriched += 1
            else:
                unchanged += 1
        return EnrichmentSummary(scanned, enriched, failed, unchanged)

    async def _enrich_one(self, patent: LibraryPatent) -> bool:
        publication = normalize_patent_number(patent.publication_number)
        page = await self.provider.lookup_publication(publication)
        if not page.hits:
            return False
        hit = page.hits[0]
        classifications = tuple(
            Classification(system="AUTO", code=code)
            for code in hit.classifications
        )
        updated = PatentPublication(
            publication_number=patent.publication_number,
            jurisdiction=patent.jurisdiction,
            kind_code=patent.kind_code,
            title=hit.title or patent.title,
            publication_date=hit.publication_date or patent.publication_date,
            original_assignees=hit.applicants or patent.original_assignees,
            current_assignees=hit.applicants or patent.current_assignees,
            classifications=classifications,
        )
        self.store.upsert_publication(updated, source=hit.source or patent.source)
        text = " ".join(
            part for part in (hit.title or "", hit.abstract or "") if part
        )
        matches = self.classifier.classify(
            text=text,
            classifications=hit.classifications,
        )
        for match in matches[:5]:
            self.store.add_technology_topic(patent.publication_number, match.name)
        return bool(hit.title or hit.applicants or hit.classifications or hit.abstract)


def _needs_enrichment(patent: LibraryPatent) -> bool:
    return not (
        patent.title
        and (patent.current_assignees or patent.original_assignees)
        and patent.classifications
    )
