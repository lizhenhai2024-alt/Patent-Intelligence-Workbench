import asyncio

import pytest

from app.core.patent_number import normalize_patent_number
from app.domain.family import FamilyType, PatentFamily, PatentPublication
from app.providers.base import (
    ProviderCapability,
    ProviderError,
    ProviderInfo,
)
from app.services.family_resolver import FamilyResolutionError, FamilyResolver


class FailingProvider:
    info = ProviderInfo(
        name="FAIL",
        capabilities=frozenset({ProviderCapability.FAMILY_EXTENDED}),
    )

    async def get_family(self, publication, family_type):
        raise ProviderError("temporary failure")


class UnsupportedProvider:
    info = ProviderInfo(
        name="NO_FAMILY",
        capabilities=frozenset({ProviderCapability.BIBLIOGRAPHY}),
    )

    async def get_family(self, publication, family_type):
        raise AssertionError("unsupported provider must not be called")


class SuccessProvider:
    info = ProviderInfo(
        name="SUCCESS",
        capabilities=frozenset(
            {
                ProviderCapability.FAMILY_SIMPLE,
                ProviderCapability.FAMILY_EXTENDED,
            }
        ),
    )

    async def get_family(self, publication, family_type):
        return PatentFamily(
            family_type=family_type,
            source="SUCCESS",
            members=[
                PatentPublication(
                    publication_number=publication.canonical,
                    jurisdiction=publication.jurisdiction,
                )
            ],
        )


def test_resolver_skips_unsupported_then_falls_back_after_failure():
    resolver = FamilyResolver(
        [UnsupportedProvider(), FailingProvider(), SuccessProvider()]
    )
    publication = normalize_patent_number("JP2024000123A")

    result = asyncio.run(
        resolver.resolve(publication, FamilyType.INPADOC_EXTENDED)
    )

    assert result.provider == "SUCCESS"
    assert [attempt.provider for attempt in result.attempts] == [
        "NO_FAMILY",
        "FAIL",
        "SUCCESS",
    ]
    assert result.attempts[0].attempted is False
    assert result.attempts[1].attempted is True


def test_resolver_raises_with_attempt_history_when_all_fail():
    resolver = FamilyResolver([FailingProvider()])
    publication = normalize_patent_number("EP1000000A1")

    with pytest.raises(FamilyResolutionError) as exc_info:
        asyncio.run(
            resolver.resolve(publication, FamilyType.INPADOC_EXTENDED)
        )

    assert exc_info.value.attempts[0].provider == "FAIL"
