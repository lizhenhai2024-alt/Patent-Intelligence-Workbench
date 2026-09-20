"""Provider-neutral patent search domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class SearchMode(StrEnum):
    PATENT_NUMBER = "PATENT_NUMBER"
    TEXT = "TEXT"
    COMPANY = "COMPANY"
    COMPANY_PORTFOLIO = "COMPANY_PORTFOLIO"
    COMPANY_TECHNOLOGY = "COMPANY_TECHNOLOGY"


@dataclass(frozen=True, slots=True)
class SearchExpression:
    applicants: tuple[str, ...] = ()
    text_terms: tuple[str, ...] = ()
    text_groups: tuple[tuple[str, ...], ...] = ()
    classification_groups: tuple[tuple[str, ...], ...] = ()
    portfolio_terms: tuple[str, ...] = ()
    portfolio_classifications: tuple[str, ...] = ()
    jurisdictions: tuple[str, ...] = ()
    published_from: date | None = None
    published_to: date | None = None


@dataclass(frozen=True, slots=True)
class SearchHit:
    publication_number: str
    jurisdiction: str
    kind_code: str | None = None
    title: str | None = None
    applicants: tuple[str, ...] = ()
    publication_date: date | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class SearchPage:
    hits: tuple[SearchHit, ...]
    total_result_count: int | None = None
    range_begin: int | None = None
    range_end: int | None = None


@dataclass(frozen=True, slots=True)
class SearchResponse:
    mode: SearchMode
    provider: str
    page: SearchPage
    normalized_query: str
    company_group_id: str | None = None
