"""Domain models exposed by the local patent library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LibraryPatent:
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
    favorite_only: bool = False
    limit: int = 500
