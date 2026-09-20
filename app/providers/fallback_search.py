"""Search-provider fallback chain with structured attempt status."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.patent_number import PatentNumber
from app.domain.search import SearchExpression, SearchHit, SearchPage
from app.providers.base import (
    ProviderAuthenticationError,
    ProviderCapability,
    ProviderConfigurationError,
    ProviderError,
    ProviderInfo,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
    SearchProvider,
)


class SearchAttemptStatus(StrEnum):
    SUCCESS = "SUCCESS"
    NO_RESULTS = "NO_RESULTS"
    UNAVAILABLE = "UNAVAILABLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class SearchProviderAttempt:
    provider: str
    status: SearchAttemptStatus
    error: str | None = None


class SearchExhaustedError(ProviderError):
    def __init__(self, attempts: tuple[SearchProviderAttempt, ...]):
        self.attempts = attempts
        details = "; ".join(
            f"{item.provider}: {item.status.value}"
            + (f" ({item.error})" if item.error else "")
            for item in attempts
        )
        super().__init__(f"所有在线检索源均不可用。已尝试：{details}")


class FallbackSearchProvider:
    """Use local cache first, then zero-config public and optional providers."""

    def __init__(self, providers: tuple[SearchProvider, ...]):
        if not providers:
            raise ValueError("At least one search provider is required.")
        self.providers = providers

    @property
    def info(self) -> ProviderInfo:
        capabilities: set[ProviderCapability] = set()
        for provider in self.providers:
            capabilities.update(provider.info.capabilities)
        return ProviderInfo(
            name="SEARCH_CHAIN",
            capabilities=frozenset(capabilities),
        )

    async def lookup_publication(self, publication: PatentNumber) -> SearchPage:
        attempts: list[SearchProviderAttempt] = []
        saw_remote_no_results = False

        for provider in self.providers:
            if ProviderCapability.PUBLICATION_LOOKUP not in provider.info.capabilities:
                attempts.append(
                    SearchProviderAttempt(
                        provider.info.name,
                        SearchAttemptStatus.UNAVAILABLE,
                        "publication lookup unsupported",
                    )
                )
                continue
            try:
                page = await provider.lookup_publication(publication)
            except ProviderError as exc:
                attempts.append(_attempt_from_error(provider.info.name, exc))
                continue
            if page.hits:
                return page
            attempts.append(
                SearchProviderAttempt(
                    provider.info.name,
                    SearchAttemptStatus.NO_RESULTS,
                )
            )
            if provider.info.name != "LOCAL_LIBRARY":
                saw_remote_no_results = True

        if saw_remote_no_results:
            return SearchPage(hits=(), total_result_count=0)
        raise SearchExhaustedError(tuple(attempts))

    async def search_publications(
        self,
        expression: SearchExpression,
        *,
        page_size: int = 25,
        page_start: int = 1,
    ) -> SearchPage:
        attempts: list[SearchProviderAttempt] = []
        local_hits: tuple[SearchHit, ...] = ()
        saw_remote_no_results = False

        for provider in self.providers:
            if ProviderCapability.SEARCH not in provider.info.capabilities:
                attempts.append(
                    SearchProviderAttempt(
                        provider.info.name,
                        SearchAttemptStatus.UNAVAILABLE,
                        "search unsupported",
                    )
                )
                continue
            try:
                page = await provider.search_publications(
                    expression,
                    page_size=page_size,
                    page_start=page_start,
                )
            except ProviderError as exc:
                attempts.append(_attempt_from_error(provider.info.name, exc))
                continue

            if provider.info.name == "LOCAL_LIBRARY":
                local_hits = page.hits
                continue

            if page.hits:
                return _merge_pages(local_hits, page, page_size)

            saw_remote_no_results = True
            attempts.append(
                SearchProviderAttempt(
                    provider.info.name,
                    SearchAttemptStatus.NO_RESULTS,
                )
            )

        if local_hits:
            return SearchPage(
                hits=local_hits[:page_size],
                total_result_count=len(local_hits),
                range_begin=1,
                range_end=min(len(local_hits), page_size),
            )
        if saw_remote_no_results:
            return SearchPage(hits=(), total_result_count=0)
        raise SearchExhaustedError(tuple(attempts))


def _attempt_from_error(
    provider: str,
    exc: ProviderError,
) -> SearchProviderAttempt:
    if isinstance(exc, (ProviderAuthenticationError, ProviderConfigurationError)):
        status = SearchAttemptStatus.AUTH_REQUIRED
    elif isinstance(exc, ProviderRateLimitError):
        status = SearchAttemptStatus.RATE_LIMITED
    elif isinstance(exc, ProviderUnavailableError):
        status = SearchAttemptStatus.UNAVAILABLE
    elif isinstance(exc, ProviderResponseError):
        status = SearchAttemptStatus.FAILED
    else:
        status = SearchAttemptStatus.FAILED
    return SearchProviderAttempt(provider, status, str(exc))


def _merge_pages(
    local_hits: tuple[SearchHit, ...],
    remote_page: SearchPage,
    page_size: int,
) -> SearchPage:
    merged: list[SearchHit] = []
    seen: set[str] = set()
    for hit in (*local_hits, *remote_page.hits):
        if hit.publication_number in seen:
            continue
        seen.add(hit.publication_number)
        merged.append(hit)
        if len(merged) >= page_size:
            break
    total = remote_page.total_result_count
    if total is not None:
        total = max(total, len(merged))
    return SearchPage(
        hits=tuple(merged),
        total_result_count=total,
        range_begin=1 if merged else None,
        range_end=len(merged) if merged else None,
    )
