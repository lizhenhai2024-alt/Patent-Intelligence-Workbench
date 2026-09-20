"""JPO Patent Information Retrieval API client.

JP is a first-class V1 jurisdiction, but the current JPO domestic API is used
primarily for authoritative Japanese application data: progress, priority,
number-reference, citation and registration information.

Cross-office patent-family resolution is not coupled to this domestic client.
The separate OPD family API is optional because new OPD-API registrations have
been closed since August 2024; V1 therefore uses EPO family data as the main
cross-jurisdiction family source and treats JPO as the JP validation source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from app.providers.base import (
    ProviderCapability,
    ProviderConfigurationError,
    ProviderError,
    ProviderInfo,
    ProviderResponseError,
)

TOKEN_URL = "https://ip-data.jpo.go.jp/auth/token"
API_BASE_URL = "https://ip-data.jpo.go.jp/api"


@dataclass(slots=True)
class JpoProvider:
    username: str | None = None
    password: str | None = None
    timeout_seconds: float = 30.0

    info = ProviderInfo(
        name="JPO_PATENT_INFO",
        capabilities=frozenset(
            {
                ProviderCapability.BIBLIOGRAPHY,
                ProviderCapability.LEGAL_STATUS,
            }
        ),
    )

    def __post_init__(self) -> None:
        self.username = self.username or os.getenv("JPO_API_USERNAME")
        self.password = self.password or os.getenv("JPO_API_PASSWORD")

    def _require_credentials(self) -> tuple[str, str]:
        if not self.username or not self.password:
            raise ProviderConfigurationError(
                "JPO API credentials are required. "
                "Set JPO_API_USERNAME and JPO_API_PASSWORD."
            )
        return self.username, self.password

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        username, password = self._require_credentials()
        try:
            response = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "password",
                    "username": username,
                    "password": password,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError("JPO access-token request failed.") from exc

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise ProviderResponseError("JPO token response did not include access_token.")
        return token

    async def _get_json(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            token = await self._access_token(client)
            try:
                response = await client.get(
                    f"{API_BASE_URL}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"JPO API request failed: {path}") from exc
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderResponseError("JPO API returned a non-object JSON response.")
            return payload

    async def get_progress_simple(self, application_number: str) -> dict[str, Any]:
        return await self._get_json(
            f"/patent/v1/app_progress_simple/{application_number}"
        )

    async def get_priority_right_info(self, application_number: str) -> dict[str, Any]:
        return await self._get_json(
            f"/patent/v1/priority_right_app_info/{application_number}"
        )

    async def get_case_number_reference(
        self,
        kind: str,
        number: str,
    ) -> dict[str, Any]:
        return await self._get_json(
            f"/patent/v1/case_number_reference/{kind}/{number}"
        )

    async def get_citation_info(self, application_number: str) -> dict[str, Any]:
        return await self._get_json(
            f"/patent/v1/cite_doc_info/{application_number}"
        )

    async def get_registration_info(self, application_number: str) -> dict[str, Any]:
        return await self._get_json(
            f"/patent/v1/registration_info/{application_number}"
        )
