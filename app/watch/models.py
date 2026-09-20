"""Domain models for company and technology patent monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class WatchEventType(StrEnum):
    NEW_FAMILY = "NEW_FAMILY"
    NEW_FAMILY_MEMBER = "NEW_FAMILY_MEMBER"
    NEW_PUBLICATION_UNRESOLVED_FAMILY = "NEW_PUBLICATION_UNRESOLVED_FAMILY"


@dataclass(frozen=True, slots=True)
class WatchRule:
    rule_id: str
    name: str
    company_group: str
    technology_terms: tuple[str, ...] = ()
    jurisdictions: tuple[str, ...] = ("CN", "JP", "EP", "US", "WO", "KR")
    enabled: bool = True
    lookback_days: int = 14
    notify_on_first_run: bool = False
    cadence_hours: int = 24

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("rule_id must not be empty")
        if not self.company_group.strip():
            raise ValueError("company_group must not be empty")
        if self.lookback_days < 1:
            raise ValueError("lookback_days must be >= 1")
        if self.cadence_hours < 1:
            raise ValueError("cadence_hours must be >= 1")


@dataclass(frozen=True, slots=True)
class WatchEvent:
    event_type: WatchEventType
    rule_id: str
    publication_number: str
    jurisdiction: str
    family_key: str | None
    family_source_id: str | None
    title: str | None
    publication_date: str | None
    detected_at: datetime
    trigger_publication: str


@dataclass(frozen=True, slots=True)
class WatchRunResult:
    rule_id: str
    baseline_created: bool
    searched_hits: int
    resolved_families: int
    events: tuple[WatchEvent, ...]
    errors: tuple[str, ...]
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class WatchRunFailure:
    rule_id: str
    error: str


@dataclass(frozen=True, slots=True)
class WatchSchedulerResult:
    due_rule_ids: tuple[str, ...]
    runs: tuple[WatchRunResult, ...]
    failures: tuple[WatchRunFailure, ...]
    started_at: datetime
    completed_at: datetime
