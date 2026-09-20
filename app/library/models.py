"""Domain models exposed by the local patent library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LibraryClassification:
    system: str
    code: str
    is_main: bool = False


@dataclass(frozen=True, slots=True)
class LibraryPriority:
    number: str
    country: str
    priority_date: date | None = None
    priority_type: str | None = None


@dataclass(frozen=True, slots=True)
class LibrarySource:
    source_type: str
    source_ref: str
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class LibraryDocument:
    path: Path
    provider: str | None
    source_url: str | None
    added_at: datetime


@dataclass(frozen=True, slots=True)
class LibraryPatent:
    # Keep the original constructor fields stable for desktop/UI compatibility.
    publication_number: str
    jurisdiction: str
    kind_code: str | None
    family_key: str | None
    family_type: str | None
    family_source: str | None
    source_family_id: str | None
    title: str | None
    application_number: str | None
    grant_number: str | None
    publication_date: date | None
    earliest_priority_number: str | None
    earliest_priority_date: date | None
    original_assignees: tuple[str, ...]
    current_assignees: tuple[str, ...]
    company_groups: tuple[str, ...]
    technology_topics: tuple[str, ...]
    projects: tuple[str, ...]
    tags: tuple[str, ...]
    pdf_paths: tuple[Path, ...]
    watch_rule_ids: tuple[str, ...]
    first_seen_at: datetime
    last_seen_at: datetime
    source: str | None
    favorite: bool = False
    note: str | None = None

    # P6 enrichment fields are additive and defaulted so older UI/test code
    # can keep constructing LibraryPatent with the V1 pre-P6 signature.
    filing_date: date | None = None
    grant_date: date | None = None
    language: str | None = None
    classifications: tuple[LibraryClassification, ...] = ()
    priorities: tuple[LibraryPriority, ...] = ()
    documents: tuple[LibraryDocument, ...] = ()
    provenance: tuple[LibrarySource, ...] = ()

    def __post_init__(self) -> None:
        if self.documents and not self.pdf_paths:
            object.__setattr__(
                self,
                "pdf_paths",
                tuple(document.path for document in self.documents),
            )
        elif self.pdf_paths and not self.documents:
            object.__setattr__(
                self,
                "documents",
                tuple(
                    LibraryDocument(
                        path=path,
                        provider=None,
                        source_url=None,
                        added_at=self.first_seen_at,
                    )
                    for path in self.pdf_paths
                ),
            )


@dataclass(frozen=True, slots=True)
class LibraryFamilySummary:
    family_key: str
    family_type: str
    source: str
    source_family_id: str | None
    earliest_priority_number: str | None
    earliest_priority_date: date | None
    member_count: int
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class LibraryQuery:
    text: str | None = None
    jurisdictions: tuple[str, ...] = ()
    company_groups: tuple[str, ...] = ()
    technology_topics: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    watch_rule_ids: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    favorite_only: bool = False
    has_pdf: bool | None = None
    limit: int = 500
