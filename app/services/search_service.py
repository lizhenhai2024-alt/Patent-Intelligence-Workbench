"""Unified search orchestration for patent number, text and company queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.company_registry import CompanyRegistry
from app.core.patent_number import PatentNumberError, normalize_patent_number
from app.core.technology_dictionary import TechnologyDictionary
from app.domain.search import SearchExpression, SearchHit, SearchMode, SearchPage, SearchResponse
from app.providers.base import SearchProvider

_SUSPENSION_PORTFOLIO_TERMS = (
    "vehicle suspension",
    "automotive suspension",
    "active suspension",
    "semi active suspension",
    "shock absorber",
    "suspension damper",
    "anti roll bar",
    "active stabilizer",
)
_SUSPENSION_PORTFOLIO_CLASSIFICATIONS = (
    "B60G13",
    "B60G15",
    "B60G17",
    "B60G21",
    "F16F9/00",
    "F16F9/10",
    "F16F9/16",
    "F16F9/18",
    "F16F9/32",
    "F16F9/34",
    "F16F9/44",
    "F16F9/46",
    "F16F9/50",
    "F16F9/512",
)
_SUSPENSION_TEXT_EVIDENCE = (
    "vehicle suspension",
    "automotive suspension",
    "active suspension",
    "semi active suspension",
    "semi-active suspension",
    "shock absorber",
    "suspension damper",
    "anti roll",
    "anti-roll",
    "stabilizer bar",
    "vehicle body motion",
    "wheel damping",
    "road disturbance",
    "ride control",
)


def _is_scoped_suspension_hit(hit: SearchHit) -> bool:
    applicant_text = " ".join(hit.applicants).casefold()
    if "clearmotion" in applicant_text or "levant power" in applicant_text:
        return True
    if any(code.upper().startswith("B60G") for code in hit.classifications):
        return True
    text = f"{hit.title or ''} {hit.abstract or ''}".casefold()
    return any(term in text for term in _SUSPENSION_TEXT_EVIDENCE)


def _filter_scoped_suspension_page(page: SearchPage) -> SearchPage:
    hits = tuple(hit for hit in page.hits if _is_scoped_suspension_hit(hit))
    return SearchPage(
        hits=hits,
        total_result_count=len(hits),
        range_begin=1 if hits else None,
        range_end=len(hits) if hits else None,
    )


@dataclass(slots=True)
class SearchService:
    provider: SearchProvider
    company_registry: CompanyRegistry
    technology_dictionary: TechnologyDictionary | None = None

    @classmethod
    def with_default_registry(cls, provider: SearchProvider) -> SearchService:
        return cls(
            provider=provider,
            company_registry=CompanyRegistry.default(),
            technology_dictionary=TechnologyDictionary.default(),
        )

    def _expand_text(
        self,
        values: tuple[str, ...],
    ) -> tuple[tuple[str, ...], ...]:
        if self.technology_dictionary is None:
            return ()
        groups: list[tuple[str, ...]] = []
        for value in values:
            expanded = self.technology_dictionary.expand(
                value,
                provider_name=self.provider.info.name,
            )
            if expanded:
                groups.extend(expanded)
            elif value.strip():
                groups.append((value.strip(),))
        return tuple(groups)

    async def search(
        self,
        query: str,
        *,
        company: str | None = None,
        portfolio_scope: str | None = None,
        technology_terms: tuple[str, ...] = (),
        jurisdictions: tuple[str, ...] = (),
        published_from: date | None = None,
        published_to: date | None = None,
        page_size: int = 25,
        page_start: int = 1,
    ) -> SearchResponse:
        raw = query.strip()

        try:
            publication = normalize_patent_number(raw)
        except PatentNumberError:
            publication = None
        if publication is not None:
            page = await self.provider.lookup_publication(publication)
            return SearchResponse(
                mode=SearchMode.PATENT_NUMBER,
                provider=_page_provider(page, self.provider.info.name),
                page=page,
                normalized_query=publication.canonical,
            )

        if not company and raw:
            try:
                group = self.company_registry.get(raw)
            except KeyError:
                group = None
            if group is not None:
                company = group.group_id
                raw = ""

        if company:
            try:
                group = self.company_registry.get(company)
            except KeyError:
                group = None
            terms = technology_terms or ((raw,) if raw else ())
            technology_context = bool(terms)
            portfolio_context = bool(portfolio_scope) and not technology_context
            applicants = (
                group.applicant_names(portfolio_scope=portfolio_scope)
                if group is not None
                else (company.strip(),)
            )
            expanded_groups = self._expand_text(terms)
            portfolio_terms: tuple[str, ...] = ()
            portfolio_classifications: tuple[str, ...] = ()
            if portfolio_context and "suspension" in portfolio_scope.casefold():
                terms = ()
                expanded_groups = ()
                portfolio_terms = _SUSPENSION_PORTFOLIO_TERMS
                portfolio_classifications = _SUSPENSION_PORTFOLIO_CLASSIFICATIONS
            elif portfolio_context:
                portfolio_groups = self._expand_text((portfolio_scope,))
                if portfolio_groups:
                    portfolio_terms = tuple(
                        term
                        for group_terms in portfolio_groups
                        for term in group_terms
                    )
                elif portfolio_scope:
                    portfolio_terms = (portfolio_scope,)
            expression = SearchExpression(
                applicants=applicants,
                text_terms=terms if not expanded_groups and not portfolio_context else (),
                text_groups=expanded_groups,
                portfolio_terms=portfolio_terms,
                portfolio_classifications=portfolio_classifications,
                jurisdictions=jurisdictions,
                published_from=published_from,
                published_to=published_to,
            )
            if technology_context:
                mode = SearchMode.COMPANY_TECHNOLOGY
            elif portfolio_context:
                mode = SearchMode.COMPANY_PORTFOLIO
            else:
                mode = SearchMode.COMPANY
            page = await self.provider.search_publications(
                expression,
                page_size=page_size,
                page_start=page_start,
            )
            if (
                portfolio_context
                and group is not None
                and "suspension" in (portfolio_scope or "").casefold()
                and any(entity.scope for entity in group.entities)
            ):
                page = _filter_scoped_suspension_page(page)
            return SearchResponse(
                mode=mode,
                provider=_page_provider(page, self.provider.info.name),
                page=page,
                normalized_query=raw,
                company_group_id=group.group_id if group is not None else None,
            )

        raw_terms = (raw,) if raw else ()
        expanded_groups = self._expand_text(raw_terms)
        expression = SearchExpression(
            text_terms=raw_terms if not expanded_groups else (),
            text_groups=expanded_groups,
            jurisdictions=jurisdictions,
            published_from=published_from,
            published_to=published_to,
        )
        page = await self.provider.search_publications(
            expression,
            page_size=page_size,
            page_start=page_start,
        )
        return SearchResponse(
            mode=SearchMode.TEXT,
            provider=_page_provider(page, self.provider.info.name),
            page=page,
            normalized_query=raw,
        )


def _page_provider(page, fallback: str) -> str:
    if page.hits and page.hits[0].source:
        return page.hits[0].source
    return fallback
