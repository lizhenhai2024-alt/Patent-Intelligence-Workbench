"""Local-library search adapter used as the first zero-cost search layer."""

from __future__ import annotations

from app.core.patent_number import PatentNumber
from app.domain.search import SearchExpression, SearchHit, SearchPage
from app.library.models import LibraryPatent, LibraryQuery
from app.library.store import SQLitePatentLibrary
from app.providers.base import ProviderCapability, ProviderInfo


class LocalLibrarySearchProvider:
    info = ProviderInfo(
        name="LOCAL_LIBRARY",
        capabilities=frozenset(
            {
                ProviderCapability.SEARCH,
                ProviderCapability.PUBLICATION_LOOKUP,
            }
        ),
    )

    def __init__(self, store: SQLitePatentLibrary):
        self.store = store

    async def lookup_publication(self, publication: PatentNumber) -> SearchPage:
        patent = self.store.get_patent(publication.canonical)
        if patent is None:
            return SearchPage(hits=(), total_result_count=0)
        return SearchPage(
            hits=(_patent_to_hit(patent),),
            total_result_count=1,
            range_begin=1,
            range_end=1,
        )

    async def search_publications(
        self,
        expression: SearchExpression,
        *,
        page_size: int = 25,
        page_start: int = 1,
    ) -> SearchPage:
        if page_size < 1:
            raise ValueError("page_size must be >= 1")
        if page_start < 1:
            raise ValueError("page_start must be >= 1")

        candidates = self.store.query(
            LibraryQuery(
                jurisdictions=expression.jurisdictions,
                limit=5000,
            )
        )
        filtered = tuple(
            patent for patent in candidates if _matches_expression(patent, expression)
        )
        start = page_start - 1
        end = start + page_size
        page = filtered[start:end]
        return SearchPage(
            hits=tuple(_patent_to_hit(patent) for patent in page),
            total_result_count=len(filtered),
            range_begin=page_start if page else None,
            range_end=page_start + len(page) - 1 if page else None,
        )


def _matches_expression(
    patent: LibraryPatent,
    expression: SearchExpression,
) -> bool:
    haystack = " ".join(
        (
            patent.publication_number,
            patent.title or "",
            *patent.original_assignees,
            *patent.current_assignees,
            *patent.company_groups,
            *patent.technology_topics,
            *patent.projects,
            *patent.tags,
        )
    ).casefold()

    if expression.applicants:
        if not any(name.casefold() in haystack for name in expression.applicants):
            return False

    if expression.text_terms:
        if not any(term.casefold() in haystack for term in expression.text_terms):
            return False

    for group in expression.text_groups:
        if group and not any(term.casefold() in haystack for term in group):
            return False

    if expression.published_from and patent.publication_date:
        if patent.publication_date < expression.published_from:
            return False
    if expression.published_to and patent.publication_date:
        if patent.publication_date > expression.published_to:
            return False

    return True


def _patent_to_hit(patent: LibraryPatent) -> SearchHit:
    applicants = patent.current_assignees or patent.original_assignees
    return SearchHit(
        publication_number=patent.publication_number,
        jurisdiction=patent.jurisdiction,
        kind_code=patent.kind_code,
        title=patent.title,
        applicants=applicants,
        classifications=tuple(item.code for item in patent.classifications),
        publication_date=patent.publication_date,
        source="LOCAL_LIBRARY",
    )
