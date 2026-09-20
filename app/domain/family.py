"""Patent family domain models.

The family is the primary V1 analysis unit. Individual national publications
remain first-class records and may belong to both a DOCDB simple family and an
INPADOC extended family when provider data is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class FamilyType(StrEnum):
    DOCDB_SIMPLE = "DOCDB_SIMPLE"
    INPADOC_EXTENDED = "INPADOC_EXTENDED"


@dataclass(frozen=True, slots=True)
class PriorityClaim:
    number: str
    country: str
    priority_date: date | None = None
    priority_type: str | None = None


@dataclass(frozen=True, slots=True)
class Classification:
    system: str
    code: str
    is_main: bool = False


@dataclass(frozen=True, slots=True)
class PatentPublication:
    publication_number: str
    jurisdiction: str
    kind_code: str | None = None
    application_number: str | None = None
    grant_number: str | None = None
    title: str | None = None
    filing_date: date | None = None
    publication_date: date | None = None
    grant_date: date | None = None
    language: str | None = None
    original_assignees: tuple[str, ...] = ()
    current_assignees: tuple[str, ...] = ()
    priorities: tuple[PriorityClaim, ...] = ()
    classifications: tuple[Classification, ...] = ()


@dataclass(slots=True)
class PatentFamily:
    family_type: FamilyType
    source: str
    source_family_id: str | None = None
    members: list[PatentPublication] = field(default_factory=list)

    @property
    def earliest_priority(self) -> PriorityClaim | None:
        claims = [
            claim
            for member in self.members
            for claim in member.priorities
            if claim.priority_date is not None
        ]
        return min(claims, key=lambda claim: claim.priority_date) if claims else None

    def member_numbers(self) -> tuple[str, ...]:
        return tuple(member.publication_number for member in self.members)

    def add_member(self, publication: PatentPublication) -> None:
        if publication.publication_number not in set(self.member_numbers()):
            self.members.append(publication)
