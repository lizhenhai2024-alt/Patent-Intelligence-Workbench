"""Patent-family provider fallback orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.core.patent_number import PatentNumber
from app.domain.family import FamilyType, PatentFamily
from app.providers.base import (
    FamilyProvider,
    ProviderCapability,
    ProviderError,
)


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    provider: str
    attempted: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FamilyResolution:
    family: PatentFamily
    provider: str
    attempts: tuple[ProviderAttempt, ...]


class FamilyResolutionError(ProviderError):
    def __init__(self, attempts: Iterable[ProviderAttempt]):
        self.attempts = tuple(attempts)
        details = "; ".join(
            f"{attempt.provider}: {attempt.error or 'not attempted'}"
            for attempt in self.attempts
        )
        super().__init__(f"No family provider succeeded. {details}")


def _required_capability(family_type: FamilyType) -> ProviderCapability:
    if family_type is FamilyType.DOCDB_SIMPLE:
        return ProviderCapability.FAMILY_SIMPLE
    if family_type is FamilyType.INPADOC_EXTENDED:
        return ProviderCapability.FAMILY_EXTENDED
    raise ValueError(f"Unsupported family type: {family_type}")


class FamilyResolver:
    """Try family providers in order without leaking provider specifics upward."""

    def __init__(self, providers: Iterable[FamilyProvider]):
        self.providers = tuple(providers)

    async def resolve(
        self,
        publication: PatentNumber,
        family_type: FamilyType,
    ) -> FamilyResolution:
        capability = _required_capability(family_type)
        attempts: list[ProviderAttempt] = []

        for provider in self.providers:
            if capability not in provider.info.capabilities:
                attempts.append(
                    ProviderAttempt(
                        provider=provider.info.name,
                        attempted=False,
                        error=f"missing capability {capability.value}",
                    )
                )
                continue

            try:
                family = await provider.get_family(publication, family_type)
            except ProviderError as exc:
                attempts.append(
                    ProviderAttempt(
                        provider=provider.info.name,
                        attempted=True,
                        error=str(exc),
                    )
                )
                continue

            attempts.append(
                ProviderAttempt(
                    provider=provider.info.name,
                    attempted=True,
                )
            )
            return FamilyResolution(
                family=family,
                provider=provider.info.name,
                attempts=tuple(attempts),
            )

        raise FamilyResolutionError(attempts)
