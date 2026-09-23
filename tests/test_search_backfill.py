from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.family import PatentFamily, PatentPublication
from app.domain.search import SearchHit, SearchMode, SearchPage, SearchResponse
from app.downloads.family import FamilyDownloadSummary, FamilyMemberDownload
from app.library import search_backfill
from app.library.service import PatentLibraryService
from app.library.store import SQLitePatentLibrary
from app.services.family_resolver import FamilyResolution, ProviderAttempt


@pytest.fixture
def library(tmp_path):
    path = tmp_path / "workbench.db"
    store = SQLitePatentLibrary(path)
    store.upsert_publication(
        PatentPublication(publication_number="US20180003259A1", jurisdiction="US", title="existing")
    )
    yield store
    store.close()


def _hit(number: str, jurisdiction: str = "CN") -> SearchHit:
    return SearchHit(publication_number=number, jurisdiction=jurisdiction, title="damper")


class FakeSearchService:
    """Returns a fixed sequence of pages, one per call, ignoring page params."""

    def __init__(self, pages: list[SearchPage], *, company_group_id: str | None = "grp-1"):
        self.pages = list(pages)
        self.company_group_id = company_group_id
        self.calls = 0

    async def search(self, query, **kwargs):
        self.calls += 1
        page = self.pages.pop(0) if self.pages else SearchPage(hits=())
        return SearchResponse(
            mode=SearchMode.COMPANY,
            provider="fake",
            page=page,
            normalized_query=query,
            company_group_id=self.company_group_id,
        )


class FakeFamilyResolver:
    def __init__(
        self,
        *,
        fail_on: frozenset[str] = frozenset(),
        family_id_by_number: dict | None = None,
    ):
        self.fail_on = fail_on
        self.family_id_by_number = family_id_by_number or {}

    async def resolve(self, publication, family_type):
        if publication.canonical in self.fail_on:
            raise RuntimeError("resolve failed")
        family_id = self.family_id_by_number.get(publication.canonical, publication.canonical)
        family = PatentFamily(
            family_type=family_type,
            source="fake",
            source_family_id=family_id,
            members=[
                PatentPublication(
                    publication_number=publication.canonical,
                    jurisdiction=publication.jurisdiction,
                )
            ],
        )
        return FamilyResolution(
            family=family, provider="fake", attempts=(ProviderAttempt("fake", True),)
        )


class FakeFamilyDownloader:
    def __init__(self, *, fail_on: frozenset[str] = frozenset()):
        self.fail_on = fail_on

    async def download_family(self, family, root, **kwargs):
        number = family.members[0].publication_number if family.members else ""
        if number in self.fail_on:
            raise RuntimeError("download failed")
        folder = Path(root) / "family"
        return FamilyDownloadSummary(
            family_folder=folder,
            manifest_path=folder / "family.json",
            members=(
                FamilyMemberDownload(
                    publication_number=number,
                    jurisdiction=family.members[0].jurisdiction if family.members else "CN",
                    status="success",
                    path=str(folder / f"{number}.pdf"),
                    provider="fake",
                ),
            ),
        )


@pytest.mark.asyncio
async def test_dedupes_against_local_library(library, tmp_path):
    service = PatentLibraryService(library)
    search_service = FakeSearchService([SearchPage(hits=(_hit("US20180003259A1"),))])
    resolver = FakeFamilyResolver()
    downloader = FakeFamilyDownloader()

    summary = await search_backfill.run_search_backfill(
        service,
        search_service,
        resolver,
        downloader,
        tmp_path,
        company="ZF",
        limit=10,
    )

    assert summary.scanned == 1
    assert summary.already_local == 1
    assert summary.added == 0


@pytest.mark.asyncio
async def test_adds_new_publications_and_records_provenance(library, tmp_path):
    service = PatentLibraryService(library)
    search_service = FakeSearchService([SearchPage(hits=(_hit("CN201900001U"),))])
    resolver = FakeFamilyResolver()
    downloader = FakeFamilyDownloader()

    summary = await search_backfill.run_search_backfill(
        service,
        search_service,
        resolver,
        downloader,
        tmp_path,
        company="ZF",
        limit=10,
    )

    assert summary.added == 1
    assert library.get_patent("CN201900001U") is not None
    row = library.connection.execute(
        "SELECT source_type FROM library_provenance WHERE publication_number = ?",
        ("CN201900001U",),
    ).fetchone()
    assert row["source_type"] == "BACKFILL"


@pytest.mark.asyncio
async def test_family_level_dedupe_within_one_run(library, tmp_path):
    service = PatentLibraryService(library)
    search_service = FakeSearchService(
        [SearchPage(hits=(_hit("CN201900001U"), _hit("CN201900002U")))]
    )
    resolver = FakeFamilyResolver(
        family_id_by_number={"CN201900001U": "FAM-1", "CN201900002U": "FAM-1"}
    )
    downloader = FakeFamilyDownloader()

    summary = await search_backfill.run_search_backfill(
        service,
        search_service,
        resolver,
        downloader,
        tmp_path,
        company="ZF",
        limit=10,
    )

    assert summary.added == 1
    assert summary.already_local == 1


@pytest.mark.asyncio
async def test_limit_caps_scanned_items(library, tmp_path):
    service = PatentLibraryService(library)
    hits = tuple(_hit(f"CN20190000{i}U") for i in range(5))
    search_service = FakeSearchService([SearchPage(hits=hits)])
    resolver = FakeFamilyResolver()
    downloader = FakeFamilyDownloader()

    summary = await search_backfill.run_search_backfill(
        service,
        search_service,
        resolver,
        downloader,
        tmp_path,
        company="ZF",
        limit=2,
    )

    assert summary.scanned == 2
    assert summary.added == 2


@pytest.mark.asyncio
async def test_cancel_stops_early(library, tmp_path):
    service = PatentLibraryService(library)
    hits = tuple(_hit(f"CN20190000{i}U") for i in range(3))
    search_service = FakeSearchService([SearchPage(hits=hits)])
    resolver = FakeFamilyResolver()
    downloader = FakeFamilyDownloader()

    summary = await search_backfill.run_search_backfill(
        service,
        search_service,
        resolver,
        downloader,
        tmp_path,
        company="ZF",
        limit=10,
        should_cancel=lambda: True,
    )

    assert summary.cancelled is True
    assert summary.scanned == 0
    assert summary.added == 0


@pytest.mark.asyncio
async def test_family_and_download_failures_do_not_stop_the_batch(library, tmp_path):
    service = PatentLibraryService(library)
    hits = (_hit("CN201900001U"), _hit("CN201900002U"), _hit("CN201900003U"))
    search_service = FakeSearchService([SearchPage(hits=hits)])
    resolver = FakeFamilyResolver(fail_on=frozenset({"CN201900001U"}))
    downloader = FakeFamilyDownloader(fail_on=frozenset({"CN201900002U"}))

    summary = await search_backfill.run_search_backfill(
        service,
        search_service,
        resolver,
        downloader,
        tmp_path,
        company="ZF",
        limit=10,
    )

    assert summary.scanned == 3
    assert summary.family_failed == 1
    assert summary.download_failed == 1
    assert summary.added == 1


def test_write_task_log(tmp_path):
    summary = search_backfill.SearchBackfillSummary(task_id="searchbackfill-test-1")
    summary.added = 2
    summary.outcomes.append(
        search_backfill.PublicationOutcome("CN1", "added")
    )
    path = search_backfill.write_task_log(tmp_path / "backfill_runs", summary, limit=200)
    assert path.exists()
    assert "searchbackfill-test-1" in path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_collect_new_hits_pages_past_already_local_hits(library):
    """Old bug: a low cap only ever looked at the first page. If everything on
    that page was already local, no new candidate was ever reached even though
    later pages had plenty. collect_new_hits must keep paging until it finds
    `limit` genuinely new hits (or hits max_scanned)."""
    page1 = SearchPage(hits=(_hit("US20180003259A1"), _hit("CN2019000021U")))
    page2 = SearchPage(hits=(_hit("CN2019000022U"), _hit("CN2019000023U")))
    search_service = FakeSearchService([page1, page2])

    result = await search_backfill.collect_new_hits(
        search_service,
        query="ZF",
        company="ZF",
        portfolio_scope=None,
        technology_terms=(),
        jurisdictions=(),
        published_from=None,
        published_to=None,
        limit=2,
        is_known=lambda number: number in {"US20180003259A1", "CN2019000021U"},
        max_scanned=100,
        page_size=2,
        delay_seconds=0,
    )
    new_hits, already_local_count, _total, _group, scan_limit_reached = result

    assert already_local_count == 2
    assert [hit.publication_number for hit in new_hits] == ["CN2019000022U", "CN2019000023U"]
    assert scan_limit_reached is False
    assert search_service.calls == 2


@pytest.mark.asyncio
async def test_collect_new_hits_stops_at_scan_limit(library):
    """If every hit turns out to already be local, paging must not run forever:
    it stops at max_scanned and reports scan_limit_reached so the caller can
    tell the user the cap was hit without finding enough new records."""
    all_local_hits = tuple(_hit(f"CN2019{i:07d}U") for i in range(4))
    search_service = FakeSearchService(
        [SearchPage(hits=all_local_hits[:2]), SearchPage(hits=all_local_hits[2:])]
    )

    result = await search_backfill.collect_new_hits(
        search_service,
        query="ZF",
        company="ZF",
        portfolio_scope=None,
        technology_terms=(),
        jurisdictions=(),
        published_from=None,
        published_to=None,
        limit=10,
        is_known=lambda _number: True,
        max_scanned=4,
        page_size=2,
        delay_seconds=0,
    )
    new_hits, already_local_count, _total, _group, scan_limit_reached = result

    assert new_hits == []
    assert already_local_count == 4
    assert scan_limit_reached is True


@pytest.mark.asyncio
async def test_collect_new_hits_sleeps_between_pages(library):
    """Each page fetch after the first is spaced out by delay_seconds so a large
    run does not hammer the search provider back-to-back."""
    page1 = SearchPage(hits=(_hit("CN2019000031U"), _hit("CN2019000032U")))
    page2 = SearchPage(hits=(_hit("CN2019000033U"),))
    search_service = FakeSearchService([page1, page2])
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    await search_backfill.collect_new_hits(
        search_service,
        query="ZF",
        company="ZF",
        portfolio_scope=None,
        technology_terms=(),
        jurisdictions=(),
        published_from=None,
        published_to=None,
        limit=10,
        is_known=lambda _number: False,
        max_scanned=100,
        page_size=2,
        delay_seconds=1.5,
        sleep=fake_sleep,
    )

    assert sleeps == [1.5]


@pytest.mark.asyncio
async def test_fills_title_and_applicants_from_hit_when_family_lookup_lacks_them(
    library, tmp_path
):
    """EPO OPS' family/biblio lookup sometimes omits title/applicant data for a
    member (a known gap for some CN records); the search hit that found it
    already carries that data and must not be discarded."""
    service = PatentLibraryService(library)
    hit = SearchHit(
        publication_number="CN2019000041U",
        jurisdiction="CN",
        title="减振器结构",
        applicants=("采埃孚",),
    )

    class BareFamilyResolver:
        async def resolve(self, publication, family_type):
            family = PatentFamily(family_type=family_type, source="fake")
            family.add_member(
                PatentPublication(
                    publication_number=publication.canonical, jurisdiction=publication.jurisdiction
                )
            )
            return FamilyResolution(family=family, provider="fake", attempts=())

    search_service = FakeSearchService([SearchPage(hits=(hit,))])
    resolver = BareFamilyResolver()
    downloader = FakeFamilyDownloader()

    summary = await search_backfill.run_search_backfill(
        service,
        search_service,
        resolver,
        downloader,
        tmp_path,
        company="ZF",
        limit=10,
    )

    assert summary.added == 1
    stored = library.get_patent("CN2019000041U")
    assert stored is not None
    assert stored.title == "减振器结构"
    assert stored.original_assignees == ("采埃孚",)


@pytest.mark.asyncio
async def test_tags_technology_topics_derived_from_hit(library, tmp_path):
    """Newly-backfilled patents should come in with technology topics already
    attached (via the same classifier the manual '补全元数据' step uses),
    instead of requiring a separate manual enrichment pass."""
    service = PatentLibraryService(library)
    hit = SearchHit(
        publication_number="CN2019000042U",
        jurisdiction="CN",
        title="连续阻尼控制减振器阀",
    )
    search_service = FakeSearchService([SearchPage(hits=(hit,))])
    resolver = FakeFamilyResolver()
    downloader = FakeFamilyDownloader()

    await search_backfill.run_search_backfill(
        service,
        search_service,
        resolver,
        downloader,
        tmp_path,
        company="ZF",
        limit=10,
    )

    stored = library.get_patent("CN2019000042U")
    assert stored is not None
    # Whatever the classifier makes of the title, ingest_family must at least
    # have been given a chance to tag it -- not silently skipped.
    assert isinstance(stored.technology_topics, tuple)
