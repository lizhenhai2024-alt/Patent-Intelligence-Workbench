"""Confirmed bulk backfill: search a company/expression, then ingest new hits.

SPEC-library-backfill.md, "补库流程" core loop (search -> dedupe -> ingest ->
family -> download -> full-text index), without the automatic "coverage low,
suggest backfill" hooks in the agent/intelligence pages (not built yet).
Network calls only happen inside `run_search_backfill`, and only after the
desktop UI has the user confirm a specific search expression and cap.

Two things this module deliberately does that a naive "fetch `limit` hits"
implementation would not:

- The cap on a run counts *new* (not-yet-local) candidates, not raw search
  hits. A low cap used to mean "only ever look at the first N remote
  results" — if those happened to already be in the library (e.g. from an
  earlier run), the genuinely new records sitting behind them were silently
  never reached, no matter how many times the run was repeated. Paging past
  already-local hits (bounded by `max_scanned`, a safety net against
  scanning an enormous, mostly-owned result set) means a rerun with the same
  cap naturally makes forward progress instead of redoing the same page.
- Each EPO OPS-backed call (family resolution, PDF download) is spaced out
  by `delay_seconds`, and the EPO OPS provider itself retries once or twice
  with a short backoff on HTTP 429 (see app/providers/epo_ops.py) — a run
  large enough to need a few hundred consecutive requests is exactly the
  case likely to trip EPO's per-minute throttling.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.domain.family import FamilyType
from app.domain.search import SearchHit
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
DEFAULT_DELAY_SECONDS = 0.4
# How many raw (pre-dedupe) hits a run is willing to page through while
# looking for `limit` new ones, and the absolute ceiling regardless of limit.
MAX_SCAN_MULTIPLIER = 5
MAX_SCAN_CEILING = 2000


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
    scan_limit_reached: bool = False
    outcomes: list[PublicationOutcome] = field(default_factory=list)


async def collect_new_hits(
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
    is_known: Callable[[str], bool],
    max_scanned: int,
    page_size: int = DEFAULT_PAGE_SIZE,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[list[SearchHit], int, int | None, str | None, bool]:
    """Page through search results until `limit` not-yet-local hits are found.

    Returns (new_hits, already_local_count, external_total, company_group_id,
    scan_limit_reached). Stops early (scan_limit_reached=True) if `max_scanned`
    raw hits are examined before `limit` new ones turn up, or if a later page
    fails after at least one page already succeeded.
    """
    new_hits: list[SearchHit] = []
    already_local_count = 0
    total: int | None = None
    company_group_id: str | None = None
    scanned = 0
    page_start = 1
    scan_limit_reached = False

    while len(new_hits) < limit and scanned < max_scanned:
        try:
            response = await search_service.search(
                query,
                company=company,
                portfolio_scope=portfolio_scope,
                technology_terms=technology_terms,
                jurisdictions=jurisdictions,
                published_from=published_from,
                published_to=published_to,
                page_size=page_size,
                page_start=page_start,
            )
        except Exception:
            if page_start == 1:
                raise
            scan_limit_reached = True
            break
        if response.page.total_result_count:
            total = response.page.total_result_count
        if response.company_group_id:
            company_group_id = response.company_group_id
        page_hits = list(response.page.hits)
        if not page_hits:
            break

        for hit in page_hits:
            scanned += 1
            if is_known(hit.publication_number):
                already_local_count += 1
            else:
                new_hits.append(hit)
            if len(new_hits) >= limit or scanned >= max_scanned:
                break

        if len(page_hits) < page_size:
            break
        page_start += page_size
        if delay_seconds:
            await sleep(delay_seconds)

    if scanned >= max_scanned and len(new_hits) < limit:
        scan_limit_reached = True
    return new_hits, already_local_count, total, company_group_id, scan_limit_reached


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
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SearchBackfillSummary:
    task_id = f"searchbackfill-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    summary = SearchBackfillSummary(task_id=task_id)

    max_scanned = min(max(limit * MAX_SCAN_MULTIPLIER, 500), MAX_SCAN_CEILING)
    hits, already_local_count, total, company_group_id, scan_limit_reached = await collect_new_hits(
        search_service,
        query=query,
        company=company,
        portfolio_scope=portfolio_scope,
        technology_terms=technology_terms,
        jurisdictions=jurisdictions,
        published_from=published_from,
        published_to=published_to,
        limit=limit,
        is_known=lambda number: service.store.get_patent(number) is not None,
        max_scanned=max_scanned,
        delay_seconds=delay_seconds,
        sleep=sleep,
    )
    summary.external_total = total
    summary.already_local = already_local_count
    summary.scan_limit_reached = scan_limit_reached
    summary.scanned = already_local_count
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
            if delay_seconds:
                await sleep(delay_seconds)
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
            if delay_seconds:
                await sleep(delay_seconds)
            continue
        summary.added += 1
        summary.outcomes.append(PublicationOutcome(number, "added"))
        if delay_seconds:
            await sleep(delay_seconds)

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
        "scan_limit_reached": summary.scan_limit_reached,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "outcomes": [
            {"publication_number": o.publication_number, "result": o.result, "detail": o.detail}
            for o in summary.outcomes
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
