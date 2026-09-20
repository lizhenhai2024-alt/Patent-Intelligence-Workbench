import asyncio

from app.core.company_registry import CompanyRegistry
from app.domain.search import SearchHit, SearchPage
from app.providers.base import (
    ProviderCapability,
    ProviderInfo,
)
from app.services.search_service import SearchService


class FakeProvider:
    info = ProviderInfo(
        name="FAKE",
        capabilities=frozenset(
            {
                ProviderCapability.SEARCH,
                ProviderCapability.PUBLICATION_LOOKUP,
            }
        ),
    )

    def __init__(self):
        self.lookup_calls = []
        self.search_calls = []

    async def lookup_publication(self, publication):
        self.lookup_calls.append(publication)
        return SearchPage(
            hits=(
                SearchHit(
                    publication_number=publication.canonical,
                    jurisdiction=publication.jurisdiction,
                    source="FAKE",
                ),
            ),
            total_result_count=1,
        )

    async def search_publications(self, expression, *, page_size=25, page_start=1):
        self.search_calls.append((expression, page_size, page_start))
        return SearchPage(hits=(), total_result_count=0)


def _registry():
    return CompanyRegistry.from_dict(
        {
            "companies": [
                {
                    "group_id": "clearmotion",
                    "display_name": "ClearMotion",
                    "core_watch": True,
                    "entities": [
                        {
                            "name": "ClearMotion, Inc.",
                            "relation": "SAME_ENTITY",
                        },
                        {
                            "name": "Bose Corporation",
                            "relation": "ACQUIRED_PATENT_PORTFOLIO",
                            "scope": "suspension portfolio only",
                        },
                    ],
                }
            ]
        }
    )


def test_patent_number_query_routes_to_direct_lookup():
    provider = FakeProvider()
    service = SearchService(provider=provider, company_registry=_registry())

    result = asyncio.run(service.search("JP 2024-123456 A"))

    assert result.mode.value == "PATENT_NUMBER"
    assert result.normalized_query == "JP2024123456A"
    assert provider.lookup_calls[0].canonical == "JP2024123456A"
    assert provider.search_calls == []


def test_company_only_query_does_not_include_scoped_portfolio():
    provider = FakeProvider()
    service = SearchService(provider=provider, company_registry=_registry())

    result = asyncio.run(service.search("", company="ClearMotion"))

    expression = provider.search_calls[0][0]
    assert result.mode.value == "COMPANY"
    assert expression.applicants == ("ClearMotion, Inc.",)


def test_company_technology_query_includes_scoped_portfolio():
    provider = FakeProvider()
    service = SearchService(provider=provider, company_registry=_registry())

    result = asyncio.run(
        service.search(
            "",
            company="ClearMotion",
            technology_terms=("active suspension",),
        )
    )

    expression = provider.search_calls[0][0]
    assert result.mode.value == "COMPANY_TECHNOLOGY"
    assert expression.applicants == (
        "ClearMotion, Inc.",
        "Bose Corporation",
    )
    assert expression.text_terms == ("active suspension",)
