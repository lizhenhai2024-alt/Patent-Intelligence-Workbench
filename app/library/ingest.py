"""Bridge Search/Family/Download/Watch results into the local library."""

from __future__ import annotations

from datetime import datetime

from app.domain.family import PatentFamily
from app.downloads.family import FamilyDownloadSummary
from app.library.store import SQLitePatentLibrary
from app.watch.models import WatchEvent


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
    family_key = library.upsert_family(family, seen_at=seen_at)
    for member in family.members:
        number = member.publication_number
        if company_group:
            library.add_company_group(number, company_group)
        for topic in technology_topics:
            library.add_technology_topic(number, topic)
        if project:
            library.add_project(number, project)
        for tag in tags:
            library.add_tag(number, tag)
    return family_key


def ingest_download_summary(
    library: SQLitePatentLibrary,
    summary: FamilyDownloadSummary,
) -> int:
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
    if library.get_patent(event.publication_number) is None:
        return False
    library.add_watch_source(
        event.publication_number,
        event.rule_id,
        event_type=event.event_type.value,
        detected_at=event.detected_at,
    )
    return True
