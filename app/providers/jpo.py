"""JPO Patent Information Retrieval API adapter contract.

JPO is a first-class V1 jurisdiction. Live endpoint mapping is intentionally
kept behind this adapter because the JPO Patent Information Retrieval APIs
require user registration, apply access limits, and expose both domestic
application information and IP5 One Portal Dossier information.

P2B will implement the concrete endpoint calls after the endpoint/field map is
frozen against the registered API specification.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.base import ProviderCapability, ProviderInfo


@dataclass(slots=True)
class JpoProvider:
    api_key: str | None = None

    info = ProviderInfo(
        name="JPO_PATENT_INFO",
        capabilities=frozenset(
            {
                ProviderCapability.BIBLIOGRAPHY,
                ProviderCapability.OPD,
                ProviderCapability.LEGAL_STATUS,
            }
        ),
    )
