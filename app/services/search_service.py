"""Unified search orchestration for patent number, text and company queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.company_registry import CompanyRegistry
from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.domain.search import (
    SearchExpression,
    SearchMode,
    SearchResponse,
)
from app.providers.base import SearchProvider


@dataclass(slots=True)
class SearchService:
    provider: SearchProvider
    company_registry: CompanyRegistry

    @classmethod
    def with_default_registry(cls, provider: SearchProvider) -> "SearchService":
        return cls(provider=provider, company_registry=CompanyRegistry.default())

    async def search(
        self,
        query: str,
        *,
        company: str | None = None,
        technology_terms: tuple[str, ...] = (),
        jurisdictions: tuple[str, ...] = (),
        published_from: date | None = None,
        published_to: date | None = None,
        page_size: int = 25,
    ) -> SearchResponse:
        raw = query.strip()

        if not company:
            try:
                publication = normalize_patent_number(raw)
            except PatentNumberError:
                publication = None
            if publication is not None:
                hit = await self.provider.lookup_publication(publication)
                return SearchResponse(
                    mode=SearchMode.PATENT_NUMBER,
                    provider=self.provider.info.name,
                    page=hit,
                    normalized_query=publication.canonical,
                )

        if company:
            group = self.company_registry.get(company)
            terms = technology_terms or ((raw,) if raw else ())
            technology_context = bool(terms)
            applicants = group.applicant_names(
                technology_context=technology_context,
            )
            expression = SearchExpression(
                applicants=applicants,
                text_terms=terms,
                jurisdictions=jurisdictions,
                published_from=published_from,
                published_to=published_to,
            )
            mode = (
                SearchMode.COMPANY_TECHNOLOGY
                if technology_context
                else SearchMode.COMPANY
            )
            page = await self.provider.search_publications(
                expression,
                page_size=page_size,
            )
            return SearchResponse(
                mode=mode,
                provider=self.provider.info.name,
                page=page,
                normalized_query=raw,
                company_group_id=group.group_id,
            )

        expression = SearchExpression(
            text_terms=(raw,) if raw else (),
            jurisdictions=jurisdictions,
            published_from=published_from,
            published_to=published_to,
        )
        page = await self.provider.search_publications(
            expression,
            page_size=page_size,
        )
        return SearchResponse(
            mode=SearchMode.TEXT,
            provider=self.provider.info.name,
            page=page,
            normalized_query=raw,
        )
