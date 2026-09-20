"""Provider contracts shared by EPO, JPO and future adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.core.patent_number import PatentNumber
from app.domain.family import FamilyType, PatentFamily


class ProviderError(RuntimeError):
    """Base error for external patent providers."""


class ProviderConfigurationError(ProviderError):
    """Raised when provider credentials or configuration are missing."""


class ProviderResponseError(ProviderError):
    """Raised when a provider response cannot be interpreted safely."""


class ProviderCapability(StrEnum):
    FAMILY_SIMPLE = "FAMILY_SIMPLE"
    FAMILY_EXTENDED = "FAMILY_EXTENDED"
    BIBLIOGRAPHY = "BIBLIOGRAPHY"
    PDF = "PDF"
    LEGAL_STATUS = "LEGAL_STATUS"
    OPD = "OPD"


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    name: str
    capabilities: frozenset[ProviderCapability]


class FamilyProvider(Protocol):
    info: ProviderInfo

    async def get_family(
        self,
        publication: PatentNumber,
        family_type: FamilyType,
    ) -> PatentFamily:
        """Return the requested patent family for one publication."""
        ...
