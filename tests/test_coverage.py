"""Tests for the coverage check service."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.company_registry import CompanyRegistry
from app.domain.family import FamilyType, PatentFamily, PatentPublication
from app.domain.search import SearchMode, SearchPage, SearchResponse
from app.library.coverage import CoverageReport, check_coverage
from app.library.store import SQLitePatentLibrary


class FakeSearchProvider:
    info = type("Info", (), {"name": "fake"})()
    _total: int | None = 100

    async def lookup_publication(self, pub):
        return SearchPage(hits=(), total_result_count=0)

    async def search_applicants(self, applicants, **kw):
        return SearchResponse(
            mode=SearchMode.COMPANY,
            provider="fake",
            page=SearchPage(hits=(), total_result_count=self._total),
            normalized_query="",
        )


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "test.db"
    s = SQLitePatentLibrary(path)
    for number, group, has_date in [
        ("US2024001A1", "kyb", True),
        ("US2024002A1", "kyb", False),
        ("US2024003A1", "kyb", True),
        ("CN2024004A1", "astemo", True),
    ]:
        s.upsert_family(
            PatentFamily(
                family_type=FamilyType.DOCDB_SIMPLE,
                source="TEST",
                source_family_id=f"F-{number}",
                members=[
                    PatentPublication(
                        publication_number=number,
                        jurisdiction=number[:2],
                        filing_date=date(2024, 1, 1) if has_date else None,
                    )
                ],
            )
        )
        s.add_company_group(number, group)
    return s


@pytest.mark.asyncio
async def test_coverage_with_external_total(store):
    provider = FakeSearchProvider()
    provider._total = 50
    registry = CompanyRegistry.default()
    service = type(
        "S",
        (),
        {
            "company_registry": registry,
            "search": provider.search_applicants,
        },
    )()
    report = await check_coverage(
        store,
        service,
        "KYB",
        technology_terms=(),
    )
    assert isinstance(report, CoverageReport)
    assert report.local_total == 3
    assert report.local_with_dates == 2
    assert report.local_without_dates == 1
    assert report.external_total == 50
    assert report.ratio == pytest.approx(3 / 50)
    assert "1 件缺申请日" in report.date_range_note


@pytest.mark.asyncio
async def test_coverage_external_unknown(store):
    provider = FakeSearchProvider()
    provider._total = None
    registry = CompanyRegistry.default()
    service = type(
        "S",
        (),
        {
            "company_registry": registry,
            "search": provider.search_applicants,
        },
    )()
    report = await check_coverage(store, service, "KYB")
    assert report.external_total is None
    assert report.ratio is None


@pytest.mark.asyncio
async def test_coverage_no_local_matches(store):
    provider = FakeSearchProvider()
    provider._total = 100
    registry = CompanyRegistry.default()
    service = type(
        "S",
        (),
        {
            "company_registry": registry,
            "search": provider.search_applicants,
        },
    )()
    report = await check_coverage(store, service, "Tenneco")
    assert report.local_total == 0
    assert report.ratio == 0.0
