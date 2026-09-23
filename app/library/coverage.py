"""Coverage check: compare local library counts against external search totals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.library.models import LibraryQuery
from app.library.store import SQLitePatentLibrary
from app.services.search_service import SearchService


@dataclass(frozen=True, slots=True)
class CoverageReport:
    company: str
    technology_terms: tuple[str, ...]
    jurisdictions: tuple[str, ...]
    external_total: int | None
    local_total: int
    local_with_dates: int
    local_without_dates: int
    ratio: float | None
    provider: str
    date_range_note: str


async def check_coverage(
    store: SQLitePatentLibrary,
    search_service: SearchService,
    company: str,
    *,
    technology_terms: tuple[str, ...] = (),
    portfolio_scope: str | None = None,
    jurisdictions: tuple[str, ...] = (),
    published_from: date | None = None,
    published_to: date | None = None,
) -> CoverageReport:
    """Query external provider for total count and local library for matching count."""
    group = None
    try:
        group = search_service.company_registry.get(company)
    except KeyError:
        pass

    company_groups = (group.group_id,) if group else ()
    local_query = LibraryQuery(
        company_groups=company_groups,
        technology_topics=technology_terms,
        jurisdictions=jurisdictions,
        limit=max(1, store.count_patents()),
    )
    local_patents = store.query(local_query)
    local_total = len(local_patents)
    local_with_dates = sum(
        1 for p in local_patents if p.filing_date or p.earliest_priority_date
    )
    local_without_dates = local_total - local_with_dates

    external_total: int | None = None
    provider_name = ""
    try:
        response = await search_service.search(
            "",
            company=group.display_name if group else company,
            portfolio_scope=portfolio_scope,
            technology_terms=technology_terms,
            jurisdictions=jurisdictions,
            published_from=published_from,
            published_to=published_to,
            page_size=1,
        )
        external_total = response.page.total_result_count
        provider_name = response.provider
    except Exception:
        pass

    ratio = None
    if external_total and external_total > 0:
        ratio = local_total / external_total

    date_note = ""
    if local_without_dates > 0:
        date_note = f"本地 {local_without_dates} 件缺申请日/公开日"

    return CoverageReport(
        company=group.display_name if group else company,
        technology_terms=technology_terms,
        jurisdictions=jurisdictions,
        external_total=external_total,
        local_total=local_total,
        local_with_dates=local_with_dates,
        local_without_dates=local_without_dates,
        ratio=ratio,
        provider=provider_name,
        date_range_note=date_note,
    )
