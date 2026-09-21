import asyncio

import pytest

from app.core.patent_number import normalize_patent_number
from app.domain.search import SearchExpression, SearchHit, SearchPage
from app.providers.base import (
    ProviderCapability,
    ProviderInfo,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.providers.fallback_search import (
    FallbackSearchProvider,
    SearchAttemptStatus,
    SearchExhaustedError,
)


class FakeProvider:
    def __init__(
        self,
        name,
        *,
        lookup_page=None,
        search_page=None,
        lookup_error=None,
        search_error=None,
    ):
        self.info = ProviderInfo(
            name=name,
            capabilities=frozenset(
                {
                    ProviderCapability.SEARCH,
                    ProviderCapability.PUBLICATION_LOOKUP,
                }
            ),
        )
        self.lookup_page = lookup_page
        self.search_page = search_page
        self.lookup_error = lookup_error
        self.search_error = search_error
        self.lookup_calls = 0
        self.search_calls = 0

    async def lookup_publication(self, publication):
        self.lookup_calls += 1
        if self.lookup_error:
            raise self.lookup_error
        return self.lookup_page or SearchPage(hits=(), total_result_count=0)

    async def search_publications(
        self,
        expression,
        *,
        page_size=25,
        page_start=1,
    ):
        self.search_calls += 1
        if self.search_error:
            raise self.search_error
        return self.search_page or SearchPage(hits=(), total_result_count=0)


def _hit(number="JP2024123456A", source="GOOGLE_PATENTS"):
    return SearchHit(
        publication_number=number,
        jurisdiction=number[:2],
        source=source,
    )


def test_lookup_stops_at_local_library_hit():
    local = FakeProvider(
        "LOCAL_LIBRARY",
        lookup_page=SearchPage(hits=(_hit(source="LOCAL_LIBRARY"),)),
    )
    public = FakeProvider(
        "GOOGLE_PATENTS",
        lookup_page=SearchPage(hits=(_hit(),)),
    )
    chain = FallbackSearchProvider((local, public))

    page = asyncio.run(
        chain.lookup_publication(normalize_patent_number("JP2024123456A"))
    )

    assert page.hits[0].source == "LOCAL_LIBRARY"
    assert local.lookup_calls == 1
    assert public.lookup_calls == 0


def test_rate_limited_provider_falls_back_to_next_provider():
    failing = FakeProvider(
        "EPO_OPS",
        search_error=ProviderRateLimitError("HTTP 429"),
    )
    public = FakeProvider(
        "GOOGLE_PATENTS",
        search_page=SearchPage(hits=(_hit(),), total_result_count=1),
    )
    chain = FallbackSearchProvider((failing, public))

    page = asyncio.run(
        chain.search_publications(SearchExpression(text_terms=("damper",)))
    )

    assert page.hits[0].source == "GOOGLE_PATENTS"
    assert failing.search_calls == 1
    assert public.search_calls == 1


def test_unavailable_provider_falls_back_without_raising():
    failing = FakeProvider(
        "EPO_OPS",
        lookup_error=ProviderUnavailableError("network down"),
    )
    public = FakeProvider(
        "GOOGLE_PATENTS",
        lookup_page=SearchPage(hits=(_hit(),), total_result_count=1),
    )
    chain = FallbackSearchProvider((failing, public))

    page = asyncio.run(
        chain.lookup_publication(normalize_patent_number("JP2024123456A"))
    )

    assert page.hits[0].source == "GOOGLE_PATENTS"


def test_all_failed_providers_return_aggregated_attempts():
    first = FakeProvider(
        "PUBLIC_A",
        search_error=ProviderUnavailableError("offline"),
    )
    second = FakeProvider(
        "PUBLIC_B",
        search_error=ProviderRateLimitError("429"),
    )
    chain = FallbackSearchProvider((first, second))

    with pytest.raises(SearchExhaustedError) as caught:
        asyncio.run(
            chain.search_publications(SearchExpression(text_terms=("damper",)))
        )

    attempts = caught.value.attempts
    assert [item.provider for item in attempts] == ["PUBLIC_A", "PUBLIC_B"]
    assert attempts[0].status is SearchAttemptStatus.UNAVAILABLE
    assert attempts[1].status is SearchAttemptStatus.RATE_LIMITED


def test_cn_lookup_refreshes_stale_local_metadata_from_remote():
    local_hit = SearchHit(
        publication_number="CN117329258A",
        jurisdiction="CN",
        title="Pressure relief poppet valve for suspension damper",
        applicants=("DREWE AUTOMOTIVE CO LTD",),
        source="LOCAL_LIBRARY",
    )
    remote_hit = SearchHit(
        publication_number="CN117329258A",
        jurisdiction="CN",
        title="用于悬架式阻尼器的释压提升阀",
        applicants=("德雷威汽车股份有限公司",),
        source="EPO_OPS",
    )
    local = FakeProvider(
        "LOCAL_LIBRARY",
        lookup_page=SearchPage(hits=(local_hit,), total_result_count=1),
    )
    remote = FakeProvider(
        "EPO_OPS",
        lookup_page=SearchPage(hits=(remote_hit,), total_result_count=1),
    )
    chain = FallbackSearchProvider((local, remote))

    page = asyncio.run(
        chain.lookup_publication(normalize_patent_number("CN117329258A"))
    )

    assert page.hits[0].source == "EPO_OPS"
    assert page.hits[0].title == "用于悬架式阻尼器的释压提升阀"
    assert page.hits[0].applicants == ("德雷威汽车股份有限公司",)
    assert remote.lookup_calls == 1


def test_search_merge_prefers_remote_metadata_for_duplicate_publication():
    local_hit = SearchHit(
        publication_number="CN117329258A",
        jurisdiction="CN",
        title="Pressure relief poppet valve for suspension damper",
        applicants=("DREWE AUTOMOTIVE CO LTD",),
        source="LOCAL_LIBRARY",
    )
    remote_hit = SearchHit(
        publication_number="CN117329258A",
        jurisdiction="CN",
        title="用于悬架式阻尼器的释压提升阀",
        applicants=("德雷威汽车股份有限公司",),
        source="EPO_OPS",
    )
    local = FakeProvider(
        "LOCAL_LIBRARY",
        search_page=SearchPage(hits=(local_hit,), total_result_count=1),
    )
    remote = FakeProvider(
        "EPO_OPS",
        search_page=SearchPage(hits=(remote_hit,), total_result_count=1),
    )
    chain = FallbackSearchProvider((local, remote))

    page = asyncio.run(
        chain.search_publications(SearchExpression(text_terms=("damper",)))
    )

    assert len(page.hits) == 1
    assert page.hits[0].source == "EPO_OPS"
    assert page.hits[0].title == "用于悬架式阻尼器的释压提升阀"
