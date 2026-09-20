"""Live zero-credential smoke test for RC2 public search fallback."""

from __future__ import annotations

import asyncio

from app.core.company_registry import CompanyRegistry
from app.core.patent_number import normalize_patent_number
from app.core.technology_dictionary import TechnologyDictionary
from app.domain.family import FamilyType
from app.providers.base import ProviderError
from app.providers.fallback_search import FallbackSearchProvider
from app.providers.google_patents_search import GooglePatentsSearchProvider
from app.services.family_resolver import FamilyResolver
from app.services.search_service import SearchService


async def run() -> None:
    google = GooglePatentsSearchProvider()
    service = SearchService(
        provider=FallbackSearchProvider((google,)),
        company_registry=CompanyRegistry.default(),
        technology_dictionary=TechnologyDictionary.default(),
    )

    number = await service.search("EP1000000A1", page_size=10)
    assert number.page.hits
    assert number.mode.value == "PATENT_NUMBER"
    print(
        "PASS patent number:",
        number.page.hits[0].publication_number,
        number.provider,
    )

    keyword = await service.search(
        "减振器",
        jurisdictions=("CN", "JP", "EP", "US", "WO", "KR"),
        page_size=10,
    )
    assert keyword.page.hits
    print(
        "PASS keyword:",
        len(keyword.page.hits),
        keyword.page.hits[0].publication_number,
        keyword.provider,
    )

    company = await service.search(
        "damper",
        company="Tenneco / Monroe",
        technology_terms=("damper",),
        jurisdictions=("CN", "JP", "EP", "US", "WO", "KR"),
        page_size=10,
    )
    assert company.page.hits
    print(
        "PASS company+technology:",
        len(company.page.hits),
        company.page.hits[0].publication_number,
        company.provider,
    )

    try:
        resolution = await FamilyResolver((google,)).resolve(
            normalize_patent_number("EP1000000A1"),
            FamilyType.DOCDB_SIMPLE,
        )
    except ProviderError as exc:
        print("SKIP simple family live provider:", exc)
    else:
        assert len(resolution.family.members) >= 2
        print(
            "PASS simple family:",
            len(resolution.family.members),
            resolution.provider,
        )


def main() -> int:
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
