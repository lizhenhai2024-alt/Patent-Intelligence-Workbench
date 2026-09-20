"""Bridge Search/Family/Download/Watch results into the local library.

These functions preserve the original lightweight API used by the desktop
layer. New code can also use PatentLibraryService directly.
"""

from __future__ import annotations

from datetime import datetime

from app.domain.family import PatentFamily
from app.domain.search import SearchResponse
from app.downloads.family import FamilyDownloadSummary
from app.library.service import PatentLibraryService
from app.library.store import SQLitePatentLibrary
from app.watch.models import WatchEvent


def ingest_search_response(
    library: SQLitePatentLibrary,
    response: SearchResponse,
    *,
    technology_topics: tuple[str, ...] = (),
    project: str | None = None,
    tags: tuple[str, ...] = (),
    seen_at: datetime | None = None,
) -> int:
    service = PatentLibraryService(library)
    stored = service.ingest_search_response(
        response,
        technology_topics=technology_topics,
        projects=(project,) if project else (),
        tags=tags,
        seen_at=seen_at,
    )
    return len(stored)


def ingest_family(
    library: SQLitePatentLibrary,
    family: PatentFamily,
    *,
    company_group: str | None = None,
    technology_topics: tuple[str, ...] = (),
    project: str | None = None,
    tags: tuple[str, ...] = (),
    seen_at: datetime | None = None,
) -> str:
    service = PatentLibraryService(library)
    return service.ingest_family(
        family,
        company_groups=(company_group,) if company_group else (),
        technology_topics=technology_topics,
        projects=(project,) if project else (),
        tags=tags,
        seen_at=seen_at,
    )


def ingest_download_summary(
    library: SQLitePatentLibrary,
    summary: FamilyDownloadSummary,
) -> int:
    """Legacy API only attaches to already archived patents."""
    attached = 0
    for member in summary.members:
        if member.status != "success" or not member.path:
            continue
        if library.get_patent(member.publication_number) is None:
            continue
        library.attach_pdf(
            member.publication_number,
            member.path,
            provider=member.provider,
            source_url=member.source_url,
        )
        attached += 1
    return attached


def ingest_watch_event(
    library: SQLitePatentLibrary,
    event: WatchEvent,
) -> bool:
    """Legacy API keeps its no-partial-record behavior for compatibility."""
    if library.get_patent(event.publication_number) is None:
        return False
    library.add_watch_source(
        event.publication_number,
        event.rule_id,
        event_type=event.event_type.value,
        detected_at=event.detected_at,
    )
    return True
