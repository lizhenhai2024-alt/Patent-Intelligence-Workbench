"""High-level operations for the local patent library."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.domain.family import PatentFamily, PatentPublication
from app.domain.search import SearchResponse
from app.downloads.family import FamilyDownloadSummary
from app.library.export import export_csv, export_xlsx
from app.library.models import EvidenceRecord, LibraryPatent, LibraryQuery
from app.library.store import SQLitePatentLibrary
from app.watch.models import WatchEvent


@dataclass(slots=True)
class PatentLibraryService:
    store: SQLitePatentLibrary

    def search(self, query: LibraryQuery | None = None) -> tuple[LibraryPatent, ...]:
        return self.store.query(query)

    def save_acquisition_evidence(
        self,
        *,
        source: str,
        source_type: str,
        markdown: str,
        title: str | None = None,
        metadata: dict[str, object] | None = None,
        publication_number: str | None = None,
        company_group: str | None = None,
        technology_topic: str | None = None,
        tags: tuple[str, ...] = (),
        captured_at: datetime | None = None,
    ) -> EvidenceRecord:
        stamp = captured_at or datetime.now(UTC)
        linked_publication = None
        if publication_number and publication_number.strip():
            linked_publication = _canonical_or_raw(publication_number)
            if self.store.get_patent(linked_publication) is None:
                jurisdiction = linked_publication[:2]
                self.store.upsert_publication(
                    _placeholder_publication(
                        linked_publication,
                        jurisdiction=jurisdiction,
                    ),
                    source="ACQUISITION",
                    seen_at=stamp,
                )
        digest = hashlib.sha256(
            f"{source}\n{linked_publication or ''}\n{markdown}".encode()
        ).hexdigest()[:24]
        record = EvidenceRecord(
            evidence_id=f"ev-{digest}",
            source=source,
            source_type=source_type.upper(),
            title=title,
            markdown=markdown,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False, default=str),
            captured_at=stamp,
            publication_number=linked_publication,
            company_group=company_group or None,
            technology_topic=technology_topic or None,
            tags=tuple(dict.fromkeys(tag.strip() for tag in tags if tag.strip())),
        )
        self.store.add_evidence(record)
        return record

    def ingest_search_response(
        self,
        response: SearchResponse,
        *,
        technology_topics: tuple[str, ...] = (),
        projects: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        seen_at: datetime | None = None,
    ) -> tuple[str, ...]:
        """Persist search hits while keeping the search query as provenance."""
        stored: list[str] = []
        query_ref = (
            f"{response.provider}|{response.mode.value}|"
            f"{response.normalized_query or '<empty>'}"
        )

        for hit in response.page.hits:
            publication_number = _canonical_or_raw(hit.publication_number)
            publication = PatentPublication(
                publication_number=publication_number,
                jurisdiction=hit.jurisdiction,
                kind_code=hit.kind_code,
                title=hit.title,
                publication_date=hit.publication_date,
                original_assignees=hit.applicants,
            )
            self.store.upsert_publication(
                publication,
                source=response.provider,
                seen_at=seen_at,
            )
            self.store.add_provenance(
                publication_number,
                "SEARCH",
                query_ref,
                seen_at=seen_at,
            )
            if response.company_group_id:
                self.store.add_company_group(
                    publication_number,
                    response.company_group_id,
                )
            for topic in technology_topics:
                self.store.add_technology_topic(publication_number, topic)
            for project in projects:
                self.store.add_project(publication_number, project)
            for tag in tags:
                self.store.add_tag(publication_number, tag)
            stored.append(publication_number)

        return tuple(stored)

    def ingest_family(
        self,
        family: PatentFamily,
        *,
        company_groups: tuple[str, ...] = (),
        technology_topics: tuple[str, ...] = (),
        projects: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        seen_at: datetime | None = None,
    ) -> str:
        """Persist a family and apply engineering classification to every member."""
        family_key = self.store.upsert_family(family, seen_at=seen_at)
        for publication_number in family.member_numbers():
            for company_group in company_groups:
                self.store.add_company_group(publication_number, company_group)
            for topic in technology_topics:
                self.store.add_technology_topic(publication_number, topic)
            for project in projects:
                self.store.add_project(publication_number, project)
            for tag in tags:
                self.store.add_tag(publication_number, tag)
        return family_key

    def ingest_download_summary(
        self,
        summary: FamilyDownloadSummary,
        *,
        seen_at: datetime | None = None,
    ) -> tuple[str, ...]:
        """Attach successful family-download files to local patent records."""
        attached: list[str] = []
        for member in summary.members:
            if member.status != "success" or not member.path:
                continue
            publication_number = _canonical_or_raw(member.publication_number)
            if self.store.get_patent(publication_number) is None:
                self.store.upsert_publication(
                    _placeholder_publication(
                        publication_number,
                        jurisdiction=member.jurisdiction,
                    ),
                    source=member.provider or "DOWNLOAD",
                    seen_at=seen_at,
                )
            self.store.attach_pdf(
                publication_number,
                member.path,
                provider=member.provider,
                source_url=member.source_url,
                added_at=seen_at,
            )
            attached.append(publication_number)
        return tuple(attached)

    def ingest_watch_event(
        self,
        event: WatchEvent,
        *,
        company_group: str | None = None,
        technology_topics: tuple[str, ...] = (),
    ) -> str:
        """Persist a Watch event without requiring family resolution to succeed."""
        publication_number = _canonical_or_raw(event.publication_number)
        if self.store.get_patent(publication_number) is None:
            self.store.upsert_publication(
                PatentPublication(
                    publication_number=publication_number,
                    jurisdiction=event.jurisdiction,
                    title=event.title,
                    publication_date=_parse_optional_date(event.publication_date),
                ),
                source="PATENT_WATCH",
                seen_at=event.detected_at,
            )
        self.store.add_watch_source(
            publication_number,
            event.rule_id,
            event_type=event.event_type.value,
            detected_at=event.detected_at,
        )
        if company_group:
            self.store.add_company_group(publication_number, company_group)
        for topic in technology_topics:
            self.store.add_technology_topic(publication_number, topic)
        return publication_number

    def export(
        self,
        destination: str | Path,
        *,
        query: LibraryQuery | None = None,
    ) -> Path:
        patents = self.store.query(query)
        path = Path(destination)
        suffix = path.suffix.casefold()
        if suffix == ".csv":
            return export_csv(patents, path)
        if suffix == ".xlsx":
            return export_xlsx(patents, path)
        raise ValueError("Export destination must end in .csv or .xlsx")


def _canonical_or_raw(value: str) -> str:
    try:
        return normalize_patent_number(value).canonical
    except PatentNumberError:
        return value.strip().upper()


def _placeholder_publication(
    publication_number: str,
    *,
    jurisdiction: str,
) -> PatentPublication:
    try:
        normalized = normalize_patent_number(publication_number)
    except PatentNumberError:
        return PatentPublication(
            publication_number=publication_number,
            jurisdiction=jurisdiction.upper(),
        )
    return PatentPublication(
        publication_number=normalized.canonical,
        jurisdiction=normalized.jurisdiction,
        kind_code=normalized.kind_code,
    )


def _parse_optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
