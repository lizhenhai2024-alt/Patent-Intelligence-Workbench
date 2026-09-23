"""Confirmed bulk backfill: search a company/expression, then ingest new hits.

SPEC-library-backfill.md, "补库流程" core loop (search -> dedupe -> ingest ->
family -> download -> full-text index), without the automatic "coverage low,
suggest backfill" hooks in the agent/intelligence pages (not built yet).
Network calls only happen inside `run_search_backfill`, and only after the
desktop UI has the user confirm a specific search expression and cap.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.domain.family import FamilyType
from app.downloads.family import FamilyDownloader, FamilyDownloadSummary
from app.library.archive import company_folder
from app.library.ingest import ingest_download_summary, ingest_family
from app.library.service import PatentLibraryService
from app.services.family_resolver import FamilyResolver
from app.services.search_service import SearchService

SOURCE_TYPE = "SEARCH"
DEFAULT_LIMIT = 200
HARD_LIMIT = 1000
DEFAULT_PAGE_SIZE = 100


@dataclass(slots=True)
class PublicationOutcome:
    publication_number: str
    result: str  # "added" | "already_local" | "family_failed" | "download_failed"
    detail: str = ""


@dataclass(slots=True)
class SearchBackfillSummary:
    task_id: str
    external_total: int | None = None
    scanned: int = 0
    already_local: int = 0
    added: int = 0
    family_failed: int = 0
    download_failed: int = 0
    cancelled: bool = False
    outcomes: list[PublicationOutcome] = field(default_factory=list)


async def collect_hits(
    search_service: SearchService,
    *,
    query: str,
    company: str | None,
    portfolio_scope: str | None,
    technology_terms: tuple[str, ...],
    jurisdictions: tuple[str, ...],
    published_from: date | None,
    published_to: date | None,
    limit: int,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list, int | None, str | None]:
    """Page through search results up to `limit` hits.

    Returns (hits, external_total, company_group_id).
    """
    hits: list = []
    total: int | None = None
    company_group_id: str | None = None
    page_start = 1
    while len(hits) < limit:
        response = await search_service.search(
            query,
            company=company,
            portfolio_scope=portfolio_scope,
            technology_terms=technology_terms,
            jurisdictions=jurisdictions,
            published_from=published_from,
            published_to=published_to,
            page_size=min(page_size, limit - len(hits)) or 1,
            page_start=page_start,
        )
        if response.page.total_result_count:
            total = response.page.total_result_count
        if response.company_group_id:
            company_group_id = response.company_group_id
        page_hits = list(response.page.hits)
        if not page_hits:
            break
        hits.extend(page_hits)
        if len(page_hits) < page_size:
            break
        page_start += page_size
    return hits[:limit], total, company_group_id


async def run_search_backfill(
    service: PatentLibraryService,
    search_service: SearchService,
    family_resolver: FamilyResolver,
    family_downloader: FamilyDownloader,
    library_root: Path,
    *,
    query: str = "",
    company: str | None = None,
    portfolio_scope: str | None = None,
    technology_terms: tuple[str, ...] = (),
    jurisdictions: tuple[str, ...] = (),
    published_from: date | None = None,
    published_to: date | None = None,
    limit: int = DEFAULT_LIMIT,
    family_type: FamilyType = FamilyType.DOCDB_SIMPLE,
    archive_folder_name: str | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> SearchBackfillSummary:
    task_id = f"searchbackfill-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    summary = SearchBackfillSummary(task_id=task_id)

    hits, total, company_group_id = await collect_hits(
        search_service,
        query=query,
        company=company,
        portfolio_scope=portfolio_scope,
        technology_terms=technology_terms,
        jurisdictions=jurisdictions,
        published_from=published_from,
        published_to=published_to,
        limit=limit,
    )
    summary.external_total = total
    total_hits = len(hits)
    processed_families: set[str] = set()
    company_root = company_folder(library_root, archive_folder_name or company or "待归类")

    for position, hit in enumerate(hits, 1):
        if should_cancel and should_cancel():
            summary.cancelled = True
            break
        summary.scanned += 1
        number = hit.publication_number
        if progress:
            progress(position, total_hits, number)
        if service.store.get_patent(number) is not None:
            summary.already_local += 1
            summary.outcomes.append(PublicationOutcome(number, "already_local"))
            continue
        try:
            patent = normalize_patent_number(number)
        except PatentNumberError as exc:
            summary.family_failed += 1
            summary.outcomes.append(PublicationOutcome(number, "family_failed", str(exc)))
            continue
        try:
            resolution = await family_resolver.resolve(patent, family_type)
            family = resolution.family
        except Exception as exc:  # provider errors vary; keep the batch going
            summary.family_failed += 1
            summary.outcomes.append(PublicationOutcome(number, "family_failed", str(exc)))
            continue
        family_key = family.source_family_id or number
        if family_key in processed_families:
            summary.already_local += 1
            summary.outcomes.append(PublicationOutcome(number, "already_local", "同族已处理"))
            continue
        processed_families.add(family_key)
        ingest_family(service.store, family, company_group=company_group_id)
        service.store.add_provenance(number, "BACKFILL", task_id)
        try:
            download_summary: FamilyDownloadSummary = await family_downloader.download_family(
                family, company_root
            )
            ingest_download_summary(service.store, download_summary)
        except Exception as exc:
            summary.download_failed += 1
            summary.outcomes.append(PublicationOutcome(number, "download_failed", str(exc)))
            continue
        summary.added += 1
        summary.outcomes.append(PublicationOutcome(number, "added"))

    return summary


def write_task_log(log_dir: Path, summary: SearchBackfillSummary, *, limit: int) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{summary.task_id}.json"
    payload = {
        "task_id": summary.task_id,
        "source": SOURCE_TYPE,
        "limit": limit,
        "external_total": summary.external_total,
        "scanned": summary.scanned,
        "already_local": summary.already_local,
        "added": summary.added,
        "family_failed": summary.family_failed,
        "download_failed": summary.download_failed,
        "cancelled": summary.cancelled,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "outcomes": [
            {"publication_number": o.publication_number, "result": o.result, "detail": o.detail}
            for o in summary.outcomes
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
