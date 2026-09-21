import asyncio

from app.core.company_registry import CompanyRegistry
from app.core.technology_dictionary import TechnologyDictionary
from app.domain.search import SearchHit, SearchPage
from app.providers.base import ProviderCapability, ProviderInfo
from app.services.search_service import SearchService, _filter_scoped_suspension_page


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


class FakeEpoProvider(FakeProvider):
    info = ProviderInfo(
        name="EPO_OPS",
        capabilities=FakeProvider.info.capabilities,
    )


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


def test_patent_number_query_ignores_stale_company_filter_and_still_uses_lookup():
    provider = FakeProvider()
    service = SearchService(provider=provider, company_registry=_registry())

    result = asyncio.run(
        service.search("CN 115123456 A", company="ClearMotion")
    )

    assert result.mode.value == "PATENT_NUMBER"
    assert provider.lookup_calls[0].canonical == "CN115123456A"
    assert provider.search_calls == []


def test_company_only_query_does_not_include_scoped_portfolio():
    provider = FakeProvider()
    service = SearchService(provider=provider, company_registry=_registry())

    result = asyncio.run(service.search("", company="ClearMotion"))

    expression = provider.search_calls[0][0]
    assert result.mode.value == "COMPANY"
    assert expression.applicants == ("ClearMotion, Inc.",)


def test_company_technology_query_does_not_unlock_scoped_portfolio():
    provider = FakeProvider()
    service = SearchService(
        provider=provider,
        company_registry=_registry(),
        technology_dictionary=TechnologyDictionary.default(),
    )

    result = asyncio.run(
        service.search(
            "",
            company="ClearMotion",
            technology_terms=("active suspension",),
        )
    )

    expression = provider.search_calls[0][0]
    assert result.mode.value == "COMPANY_TECHNOLOGY"
    assert expression.applicants == ("ClearMotion, Inc.",)
    assert expression.text_terms == ()
    assert expression.text_groups
    assert expression.text_groups[0][0] == "active suspension"


def test_company_unknown_technology_does_not_unlock_scoped_portfolio():
    provider = FakeProvider()
    service = SearchService(
        provider=provider,
        company_registry=_registry(),
        technology_dictionary=TechnologyDictionary.default(),
    )

    result = asyncio.run(
        service.search(
            "speaker",
            company="ClearMotion",
            technology_terms=("speaker",),
        )
    )

    expression = provider.search_calls[0][0]
    assert result.mode.value == "COMPANY_TECHNOLOGY"
    assert expression.applicants == ("ClearMotion, Inc.",)
    assert expression.text_terms == ()
    assert expression.text_groups == (("speaker",),)


def test_multilingual_dictionary_expands_chinese_company_technology_query():
    provider = FakeEpoProvider()
    service = SearchService(
        provider=provider,
        company_registry=_registry(),
        technology_dictionary=TechnologyDictionary.default(),
    )

    asyncio.run(
        service.search(
            "背压控制",
            company="ClearMotion",
            technology_terms=("先导阀", "背压控制"),
        )
    )

    expression = provider.search_calls[0][0]
    assert expression.text_terms == ()
    assert (
        "pilot valve",
        "solenoid valve",
        "external control valve",
    ) in expression.text_groups
    assert ("back pressure", "back pressure chamber") in expression.text_groups


def test_typed_company_name_routes_to_company_search():
    provider = FakeProvider()
    service = SearchService(provider=provider, company_registry=_registry())

    result = asyncio.run(service.search("ClearMotion"))

    expression = provider.search_calls[0][0]
    assert result.mode.value == "COMPANY"
    assert result.company_group_id == "clearmotion"
    assert expression.applicants == ("ClearMotion, Inc.",)
    assert expression.text_terms == ()


def test_arbitrary_company_name_is_searched_as_exact_applicant():
    provider = FakeProvider()
    service = SearchService(provider=provider, company_registry=_registry())

    result = asyncio.run(
        service.search("", company="Example Automotive Technology Co., Ltd.")
    )

    expression = provider.search_calls[0][0]
    assert result.mode.value == "COMPANY"
    assert result.company_group_id is None
    assert expression.applicants == ("Example Automotive Technology Co., Ltd.",)
    assert expression.text_terms == ()


def test_company_portfolio_search_uses_suspension_scope_and_scoped_entity():
    provider = FakeEpoProvider()
    service = SearchService(
        provider=provider,
        company_registry=_registry(),
        technology_dictionary=TechnologyDictionary.default(),
    )

    result = asyncio.run(
        service.search(
            "",
            company="ClearMotion",
            portfolio_scope="suspension portfolio",
        )
    )

    expression = provider.search_calls[0][0]
    assert result.mode.value == "COMPANY_PORTFOLIO"
    assert expression.applicants == ("ClearMotion, Inc.", "Bose Corporation")
    assert expression.text_terms == ()
    assert expression.text_groups == ()
    assert "vehicle suspension" in expression.portfolio_terms
    assert "shock absorber" in expression.portfolio_terms
    assert "suspension" not in expression.portfolio_terms
    assert "damper" not in expression.portfolio_terms
    assert "B60G13" in expression.portfolio_classifications
    assert "F16F9/46" in expression.portfolio_classifications
    assert expression.portfolio_terms == (
        "vehicle suspension",
        "automotive suspension",
        "active suspension",
        "semi active suspension",
        "shock absorber",
        "suspension damper",
        "anti roll bar",
        "active stabilizer",
    )

def test_default_registry_routes_ftl_alias_to_company_search():
    provider = FakeProvider()
    service = SearchService(
        provider=provider,
        company_registry=CompanyRegistry.default(),
    )
    result = asyncio.run(service.search("一汽东机工"))
    expression = provider.search_calls[0][0]
    assert result.mode.value == "COMPANY"
    assert result.company_group_id == "ftl"
    assert "一汽东机工" in expression.applicants
    assert "富奥东机工" in expression.applicants


def test_scoped_suspension_filter_rejects_bose_acoustic_false_positive():
    page = SearchPage(
        hits=(
            SearchHit(
                publication_number="US2023188895A1",
                jurisdiction="US",
                title="Balanced acoustic device with passive radiators",
                applicants=("Bose Corporation",),
            ),
            SearchHit(
                publication_number="US2016129749A1",
                jurisdiction="US",
                title="Variable Tracking Active Suspension System",
                applicants=("Bose Corporation",),
                classifications=("B60G17/016",),
            ),
            SearchHit(
                publication_number="WO2026169591A1",
                jurisdiction="WO",
                title="Motion primitive framework for multimedia integration",
                applicants=("ClearMotion, Inc.",),
            ),
        ),
        total_result_count=3,
    )

    filtered = _filter_scoped_suspension_page(page)

    assert [hit.publication_number for hit in filtered.hits] == [
        "US2016129749A1",
        "WO2026169591A1",
    ]
