import asyncio
from pathlib import Path

from app.domain.family import PatentPublication
from app.domain.search import SearchHit, SearchPage
from app.library.enrichment import LibraryEnrichmentService
from app.library.store import SQLitePatentLibrary
from app.providers.base import ProviderCapability, ProviderInfo


class FakeLookupProvider:
    info = ProviderInfo(
        name="FAKE",
        capabilities=frozenset({ProviderCapability.PUBLICATION_LOOKUP}),
    )

    async def lookup_publication(self, publication):
        return SearchPage(
            hits=(
                SearchHit(
                    publication_number=publication.canonical,
                    jurisdiction=publication.jurisdiction,
                    title="Pilot valve damper",
                    abstract="Pilot pressure chamber controls a floating piston.",
                    applicants=("Example Assignee",),
                    classifications=("F16F9/46",),
                    source="FAKE",
                ),
            ),
            total_result_count=1,
        )


def test_library_enrichment_fills_metadata_and_topics(tmp_path: Path):
    store = SQLitePatentLibrary(tmp_path / "library.db")
    store.upsert_publication(
        PatentPublication(
            publication_number="US20240003399A1",
            jurisdiction="US",
        ),
        source="LOCAL",
    )
    service = LibraryEnrichmentService(store, FakeLookupProvider())
    summary = asyncio.run(service.enrich_incomplete(limit=10))
    patent = store.get_patent("US20240003399A1")

    assert summary.scanned == 1
    assert summary.enriched == 1
    assert patent is not None
    assert patent.title == "Pilot valve damper"
    assert patent.current_assignees == ("Example Assignee",)
    assert any(item.code == "F16F9/46" for item in patent.classifications)
    assert "Pilot Valve" in patent.technology_topics
    assert "Floating Piston" in patent.technology_topics
    store.close()
